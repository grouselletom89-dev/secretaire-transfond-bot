import os
import discord
from dotenv import load_dotenv

# Charger les variables d'environnement du fichier .env
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

# --- Configuration des Intents ---
# Les "intents" définissent les événements que votre bot doit écouter.
# Nous avons besoin de 'message_content' pour lire les messages.
intents = discord.Intents.default()
intents.message_content = True  # Activé sur le portail Discord

# Initialiser le client du bot
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    """S'exécute quand le bot est connecté et prêt."""
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('------')

@client.event
async def on_message(message):
    """S'exécute à chaque message reçu."""
    
    # Ne pas répondre aux messages du bot lui-même
    if message.author == client.user:
        return

    # Commande de test simple
    if message.content == '!ping':
        await message.channel.send('Pong !')

    # Ajoutez d'autres commandes ici
    # if message.content.startswith('!bonjour'):
    #     await message.channel.send(f'Bonjour {message.author.mention} !')

# Lancer le bot
if TOKEN is None:
    print("Erreur : Le DISCORD_TOKEN n'est pas trouvé.")
    print("Assurez-vous d'avoir un fichier .env ou une variable d'environnement sur Railway.")
else:
    client.run(TOKEN)