import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import re
from datetime import datetime, timedelta, timezone
import json
import os

from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="/", intents=intents)
tree = bot.tree

RAID_DATA_FILE = "raid_data.json"

GUILD_ID = 1295255290530238475

EMOJI_TO_ROLE = {
    "🛡️": "Tank",
    "❤️": "Healer",
    "🌑": "Shadowcaller",
    "🔥": "Flamígero o pollo",
    "❄️": "Frost"
}

ROLE_LIMITS = {
    "Tank": 1,
    "Healer": 1,
    "Shadowcaller": 1,
    "Flamígero o pollo": 1,
    "Frost": 1
}

EN_COLA_EMOJI = "📥"
raid_participantes = {}
raid_hilos = {}
DATA_FILE = "raids_guardadas.json"

if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        raid_participantes = json.load(f)
        for mid, datos in raid_participantes.items():
            hilo_id = datos.get("hilo_id")
            if hilo_id:
                raid_hilos[int(mid)] = hilo_id

def guardar_datos():
    with open(DATA_FILE, "w") as f:
        json.dump(raid_participantes, f, indent=2)

def generar_embed(nombre, data):
    embed = discord.Embed(
        title=f"📣 CONTENT {nombre}",
        description="SET PVE T8.1+\nREACCIONAR AL MENSAJE PARA ANOTARTE\nSALIMOS DESDE HO ABSOLUTE CUANDO SE LLENEN ROLES\nLOS ESPERO HASTA LA HORA INDICADA",
        color=0x8e44ad
    )

    if data.get('hora'):
        # Hora de la raid (en UTC)
        hora_raid_str = data['hora']
        # Obtener la hora actual en UTC
        ahora_utc = datetime.now(timezone.utc)

        # Crear datetime de la raid para hoy
        hora_raid = datetime.strptime(hora_raid_str, "%H:%M").replace(
            year=ahora_utc.year,
            month=ahora_utc.month,
            day=ahora_utc.day,
            tzinfo=timezone.utc
    )

    # Si ya pasó, se asume que es para mañana
    if hora_raid < ahora_utc:
        hora_raid += timedelta(days=1)

        embed.add_field(name="⏰ Hora", value=f"{hora_raid_str} UTC", inline=False)

        # Calcular el tiempo restante
        ahora_utc = datetime.now(timezone.utc)
        tiempo_restante = hora_raid - ahora_utc

        # Si la hora de la raid ya pasó o está muy cerca, no mostrar el contador
        if tiempo_restante.total_seconds() > 0:
            horas_restantes = tiempo_restante.seconds // 3600
            minutos_restantes = (tiempo_restante.seconds % 3600) // 60
            embed.add_field(
                name="⏳ Tiempo restante",
                value=f"{horas_restantes} horas y {minutos_restantes} minutos",
                inline=False
            )
        else:
            embed.add_field(name="⏳ Tiempo restante", value="Las grupales ya han comenzado o la hora es pasada.", inline=False)

    texto = ""

    filas = [
        ["🛡️"],                         # Roles principales
        ["❤️"],                   # Soporte
        ["🌑"],                   # DPS especiales
        ["🔥", "❄️"],                                     # DPS genérico
    ]

    for fila in filas:
        # Línea con rol + conteo
        linea = ""
        for emoji in fila:
            rol = EMOJI_TO_ROLE[emoji]
            jugadores = data['roles'].get(rol, [])
            ocupados = len(jugadores)
            total = ROLE_LIMITS[rol]
            linea += f"{emoji} {rol} ({ocupados}/{total})   "
        texto += linea.strip() + "\n"

        # Línea con nombres
        nombres_linea = ""
        for emoji in fila:
            rol = EMOJI_TO_ROLE[emoji]
            jugadores = data['roles'].get(rol, [])
            if jugadores:
                nombres = ", ".join([f"{n}" for i, n in enumerate(jugadores)])
                nombres_linea += f"{emoji}: {nombres}   "
        if nombres_linea:
            texto += nombres_linea.strip() + "\n"

    # Suplentes
    if data['cola']:
        texto += "\n📥 **Suplentes:**\n"
        texto += ", ".join([f"{i+1}. {n}" for i, n in enumerate(data['cola'])])
    else:
        texto += "\n📥 **Suplentes:** -"

    embed.add_field(name="👥 Composición", value=texto.strip(), inline=False)
    embed.set_footer(text="💡Tip: ¡Si no estás mencionado en el ping no vas! (no cuenta decirlo en el hilo)")

    return embed


@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)
    await tree.sync()
    print(f"✅ Bot conectado como {bot.user}")

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id:
        return

    mensaje_id = payload.message_id
    canal = bot.get_channel(payload.channel_id)
    if not canal:
        return

    user = await bot.fetch_user(payload.user_id)
    emoji = str(payload.emoji)

    if mensaje_id not in raid_participantes:
        return

    data = raid_participantes[mensaje_id]
    nombre = user.mention

    # Remover al usuario de cualquier otro rol o de la cola
    for jugadores in data["roles"].values():
        if nombre in jugadores:
            jugadores.remove(nombre)
    if nombre in data["cola"]:
        data["cola"].remove(nombre)

    if emoji in EMOJI_TO_ROLE:
        rol = EMOJI_TO_ROLE[emoji]
        jugadores = data["roles"][rol]
        if len(jugadores) < ROLE_LIMITS[rol]:
            jugadores.append(nombre)
        else:
            data["cola"].append(nombre)
    elif emoji == EN_COLA_EMOJI:
        data["cola"].append(nombre)

    else:
        return

    # Editar el embed del mensaje
    try:
        mensaje = await canal.fetch_message(mensaje_id)
        nuevo_embed = generar_embed(data["nombre"], data)
        await mensaje.edit(embed=nuevo_embed)
        guardar_datos()
    except Exception as e:
        print(f"⚠️ Error actualizando embed tras reacción: {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    if payload.user_id == bot.user.id:
        return

    mensaje_id = payload.message_id
    canal = bot.get_channel(payload.channel_id)
    if not canal or mensaje_id not in raid_participantes:
        return

    user = await bot.fetch_user(payload.user_id)
    nombre = user.mention
    emoji = str(payload.emoji)

    data = raid_participantes[mensaje_id]

    # Remover al usuario de su rol o cola, si estaba
    if emoji in EMOJI_TO_ROLE:
        rol = EMOJI_TO_ROLE[emoji]
        if nombre in data["roles"].get(rol, []):
            data["roles"][rol].remove(nombre)
    elif emoji == EN_COLA_EMOJI:
        if nombre in data["cola"]:
            data["cola"].remove(nombre)
    elif emoji == SALIR_EMOJI:
        # Nada que hacer, ya fue removido
        pass
    else:
        return

    # Actualizar el embed
    try:
        mensaje = await canal.fetch_message(mensaje_id)
        nuevo_embed = generar_embed(data["nombre"], data)
        await mensaje.edit(embed=nuevo_embed)
        guardar_datos()
    except Exception as e:
        print(f"⚠️ Error actualizando embed tras quitar reacción: {e}")


@tree.command(name="ping", description="Crear plantilla de raid", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(nombre="Nombre de la plantilla", hora="Hora en formato HH:MM (UTC)")
@app_commands.choices(nombre=[app_commands.Choice(name="GRUPALES", value="GRUPALES")])
async def ping(interaction: discord.Interaction, nombre: app_commands.Choice[str], hora: str = None):
    try:
        if not any(role.name == "Raider" for role in interaction.user.roles):
            await interaction.response.send_message("🚫 No tenés permiso para usar este comando. Solo miembros con el rol 'Raider' pueden hacerlo.", ephemeral=True)
            return

        if hora and not re.match(r"^\d{2}:\d{2}$", hora):
            await interaction.response.send_message("❌ Formato de hora inválido. Usa HH:MM (UTC).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)  # ⬅️ Esto da más tiempo

        ahora_utc = datetime.now(timezone.utc).strftime("%H:%M")
        print(f"[{ahora_utc} UTC] Ping recibido para plantilla '{nombre.value}'")

        plantilla = nombre.value
        data = {
            "nombre": plantilla,
            "hora": hora,
            "roles": {rol: [] for rol in ROLE_LIMITS},
            "cola": []
        }

        embed = generar_embed(plantilla, data)
        mensaje = await interaction.channel.send(embed=embed)

        data["mensaje_id"] = mensaje.id
        data["canal_id"] = mensaje.channel.id
        raid_participantes[mensaje.id] = data
        guardar_datos()

        for emoji in EMOJI_TO_ROLE.keys():
            await mensaje.add_reaction(emoji)
        await mensaje.add_reaction(EN_COLA_EMOJI)

        await interaction.followup.send("✅ Raid creada exitosamente.", ephemeral=True)

    except Exception as e:
        print(f"Error en /ping: {e}")
        try:
            await interaction.followup.send("⚠️ Ocurrió un error al crear la raid.", ephemeral=True)
        except:
            pass  # Por si ya se envió algo

# Crear un hilo para preguntas
    try:
        thread = await mensaje.create_thread(
            name=f"Preguntas - {plantilla}",
            auto_archive_duration=1440  # 24 horas
        )
        await thread.send("💬 Cualquier duda que tengan háganla aquí.")

    except Exception as e:
        print(f"⚠️ Error creando el hilo de preguntas: {e}")


@tree.command(name="actualizar", description="Actualizar embed de la raid", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(mensaje_id="ID del mensaje de la raid")
async def actualizar(interaction: discord.Interaction, mensaje_id: str):
    try:
        mensaje_id = int(mensaje_id)
        if mensaje_id not in raid_participantes:
            await interaction.response.send_message("🚫 No se encontró una raid con ese mensaje ID.", ephemeral=True)
            return

        datos = raid_participantes[mensaje_id]
        canal = interaction.channel
        mensaje = await canal.fetch_message(mensaje_id)
        embed = generar_embed(datos['nombre'], datos)
        await mensaje.edit(embed=embed, view=crear_vista(mensaje_id))
        await interaction.response.send_message("🔄 Embed actualizado correctamente.", ephemeral=True)
    except Exception as e:
        print(f"Error en /actualizar: {e}")
        await interaction.response.send_message("⚠️ Error al actualizar el embed.", ephemeral=True)

@tree.command(name="ver_raid", description="Ver detalles de una raid activa", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(mensaje_id="ID del mensaje de la raid")
async def ver_raid(interaction: discord.Interaction, mensaje_id: str):
    try:
        mensaje_id = int(mensaje_id)
        if mensaje_id not in raid_participantes:
            await interaction.response.send_message("🚫 No se encontró una raid con ese mensaje ID.", ephemeral=True)
            return

        datos = raid_participantes[mensaje_id]
        embed = generar_embed(datos['nombre'], datos)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        print(f"Error en /ver_raid: {e}")
        await interaction.response.send_message("⚠️ Error al mostrar la raid.", ephemeral=True)

@tree.command(name="estado_roles", description="Ver espacios disponibles por rol en una raid", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(mensaje_id="ID del mensaje de la raid")
async def estado_roles(interaction: discord.Interaction, mensaje_id: str):
    try:
        mensaje_id = int(mensaje_id)
        if mensaje_id not in raid_participantes:
            await interaction.response.send_message("🚫 No se encontró una raid con ese mensaje ID.", ephemeral=True)
            return

        datos = raid_participantes[mensaje_id]
        texto = "**Estado de roles disponibles:**\n"
        for rol in ROLE_LIMITS:
            ocupados = len(datos['roles'].get(rol, []))
            total = ROLE_LIMITS[rol]
            texto += f"- {rol}: {ocupados}/{total} ocupados ({total - ocupados} libres)\n"

        await interaction.response.send_message(texto, ephemeral=True)
    except Exception as e:
        print(f"Error en /estado_roles: {e}")
        await interaction.response.send_message("⚠️ Error al obtener el estado de roles.", ephemeral=True)

@tree.command(name="reload_vista", description="Forzar recarga visual del embed y los botones", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(mensaje_id="ID del mensaje de la raid")
async def reload_vista(interaction: discord.Interaction, mensaje_id: str):
    try:
        mensaje_id = int(mensaje_id)
        if mensaje_id not in raid_participantes:
            await interaction.response.send_message("🚫 No se encontró una raid con ese mensaje ID.", ephemeral=True)
            return

        datos = raid_participantes[mensaje_id]
        canal = interaction.channel
        mensaje = await canal.fetch_message(mensaje_id)
        embed = generar_embed(datos['nombre'], datos)

        # Forzar la recarga de vista
        await mensaje.edit(embed=embed, view=crear_vista(mensaje_id))
        await interaction.response.send_message("🔁 Vista recargada correctamente.", ephemeral=True)

        hilo_id = raid_hilos.get(mensaje_id)
        if hilo_id:
            hilo = interaction.guild.get_thread(hilo_id)
            if hilo:
                await hilo.send("🔁 Vista recargada. Si no veías los botones correctamente, ya deberían estar bien.")

    except Exception as e:
        print(f"Error en /reload_vista: {e}")
        await interaction.response.send_message("⚠️ Error al recargar la vista.", ephemeral=True)

bot.run(TOKEN)
