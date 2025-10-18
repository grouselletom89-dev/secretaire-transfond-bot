import os
import discord
import json
from discord.ui import Button, View, Modal, TextInput
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build, HttpError

# --- Chargement des variables d'environnement ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GOOGLE_SHEET_ID = os.getenv('GOOGLE_SHEET_ID')
GOOGLE_CREDS_JSON_STR = os.getenv('GOOGLE_CREDS_JSON')

# --- ID du salon pour le panneau d'administration ---
# Remplacez par l'ID de votre salon
ADMIN_CHANNEL_ID = 1429100071789793371


# Vérifier si les variables critiques sont chargées
if not all([TOKEN, GOOGLE_SHEET_ID, GOOGLE_CREDS_JSON_STR]):
    print("ERREUR CRITIQUE : Variables d'environnement manquantes.")
    print("Vérifiez DISCORD_TOKEN, GOOGLE_SHEET_ID, et GOOGLE_CREDS_JSON sur Railway.")
    exit()

# --- Configuration des Intents Discord ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# --- Authentification Google ---
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

def get_google_services():
    """Charge les identifiants et retourne les services Sheets et Drive."""
    try:
        creds_info = json.loads(GOOGLE_CREDS_JSON_STR)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        return drive_service, sheets_service
    except Exception as e:
        print(f"Erreur lors de l'authentification Google : {e}")
        return None, None

# --- Boîte de dialogue (Modal) pour entrer l'email ---
class EmailModal(Modal, title='Partage Google Sheet'):
    
    email_input = TextInput(
        label='Adresse email à ajouter',
        placeholder='exemple@gmail.com',
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Appelé lorsque l'utilisateur soumet la boîte de dialogue."""
        email = self.email_input.value
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        drive_service, _ = get_google_services()
        
        if not drive_service:
            await interaction.followup.send("Erreur : Impossible de se connecter aux services Google. Vérifiez les logs Railway.", ephemeral=True)
            return

        try:
            permission = {
                'type': 'user',
                'role': 'writer',
                'emailAddress': email
            }
            
            drive_service.permissions().create(
                fileId=GOOGLE_SHEET_ID,
                body=permission,
                sendNotificationEmail=True
            ).execute()
            
            await interaction.followup.send(f"Succès ! L'accès éditeur a été donné à `{email}`.", ephemeral=True)
            
        except HttpError as error:
            print(f"Erreur API Google : {error}")
            await interaction.followup.send(f"Erreur : Impossible de partager le document. L'email est-il correct ?\n`{error}`", ephemeral=True)
        except Exception as e:
            print(f"Erreur inattendue : {e}")
            await interaction.followup.send(f"Une erreur inconnue est survenue : `{e}`", ephemeral=True)

# --- Vue persistante avec le bouton ---
class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None) 

    @discord.ui.button(label='Ajouter un Éditeur', style=discord.ButtonStyle.success, custom_id='add_editor_button')
    async def add_editor_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmailModal())

# --- Événements du Bot ---

@client.event
async def on_ready():
    """S'exécute quand le bot est connecté et prêt."""
    
    # ÉTAPE 1 : Enregistrer la vue persistante
    # Doit être fait avant de manipuler des messages avec cette vue
    client.add_view(AdminPanelView())
    
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('------')
    print(f"Recherche du panneau d'administration dans le salon {ADMIN_CHANNEL_ID}...")

    # ÉTAPE 2 : Définir le contenu du panneau
    embed = discord.Embed(
        title="Panneau d'administration - Sécrétaire TransFond",
        description="Utilisez le bouton ci-dessous pour gérer les accès au Google Sheet.",
        color=discord.Color.blue()
    )
    view = AdminPanelView()

    # ÉTAPE 3 : Trouver le salon
    try:
        channel = await client.fetch_channel(ADMIN_CHANNEL_ID)
        if not channel:
            print(f"Erreur : Impossible de trouver le salon avec l'ID {ADMIN_CHANNEL_ID}.")
            return
            
        if not isinstance(channel, discord.TextChannel):
            print(f"Erreur : L'ID {ADMIN_CHANNEL_ID} n'est pas un salon textuel.")
            return

        # ÉTAPE 4 : Chercher un ancien panneau
        panel_message = None
        async for message in channel.history(limit=50):
            # Chercher un message du bot qui contient un embed avec le bon titre
            if message.author == client.user and message.embeds and message.embeds[0].title == embed.title:
                panel_message = message
                break  # On a trouvé le message, on arrête de chercher
        
        # ÉTAPE 5 : Mettre à jour l'ancien panneau ou en créer un nouveau
        if panel_message:
            await panel_message.edit(embed=embed, view=view)
            print(f"Panneau d'administration mis à jour dans le salon #{channel.name}.")
        else:
            await channel.send(embed=embed, view=view)
            print(f"Nouveau panneau d'administration créé dans le salon #{channel.name}.")

    except discord.errors.Forbidden:
        print(f"Erreur : Le bot n'a pas les permissions pour lire ou écrire dans le salon {ADMIN_CHANNEL_ID}.")
    except Exception as e:
        print(f"Erreur inattendue lors de la mise à jour du panneau : {e}")


@client.event
async def on_message(message):
    """S'exécute à chaque message reçu."""
    
    if message.author == client.user:
        return

    # Commande de test
    if message.content == '!ping':
        await message.channel.send('Pong !')

    # Commande manuelle (au cas où)
    if message.content == '!setup_panel':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("Vous n'avez pas la permission de faire ça.", delete_after=10)
            return
        
        embed = discord.Embed(
            title="Panneau d'administration - Sécrétaire TransFond",
            description="Utilisez le bouton ci-dessous pour gérer les accès au Google Sheet.",
            color=discord.Color.blue()
        )
        await message.channel.send(embed=embed, view=AdminPanelView())
        await message.delete() # Supprime la commande pour garder le salon propre

# --- Lancement ---
client.run(TOKEN)
