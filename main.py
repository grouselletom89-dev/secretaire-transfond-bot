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
        # Charger les identifiants depuis la variable d'environnement (format JSON)
        creds_info = json.loads(GOOGLE_CREDS_JSON_STR)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        
        # Construire les services
        drive_service = build('drive', 'v3', credentials=creds)
        sheets_service = build('sheets', 'v4', credentials=creds)
        
        return drive_service, sheets_service
    except Exception as e:
        print(f"Erreur lors de l'authentification Google : {e}")
        return None, None

# --- Boîte de dialogue (Modal) pour entrer l'email ---
class EmailModal(Modal, title='Partage Google Sheet'):
    
    # Champ de saisie pour l'email
    email_input = TextInput(
        label='Adresse email à ajouter',
        placeholder='exemple@gmail.com',
        style=discord.TextStyle.short,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        """Appelé lorsque l'utilisateur soumet la boîte de dialogue."""
        email = self.email_input.value
        
        # Indiquer que le bot réfléchit (réponse différée)
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        drive_service, _ = get_google_services()
        
        if not drive_service:
            await interaction.followup.send("Erreur : Impossible de se connecter aux services Google. Vérifiez les logs Railway.", ephemeral=True)
            return

        try:
            # Créer la permission de partage (rôle 'writer' = 'éditeur')
            permission = {
                'type': 'user',
                'role': 'writer',
                'emailAddress': email
            }
            
            drive_service.permissions().create(
                fileId=GOOGLE_SHEET_ID,
                body=permission,
                sendNotificationEmail=True  # Envoyer un email à la personne
            ).execute()
            
            # Succès !
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
        # persistent=True signifie que la vue restera active même après un redémarrage du bot
        super().__init__(timeout=None) 

    @discord.ui.button(label='Ajouter un Éditeur', style=discord.ButtonStyle.success, custom_id='add_editor_button')
    async def add_editor_button(self, interaction: discord.Interaction, button: Button):
        """Appelé lorsque quelqu'un clique sur le bouton."""
        # Ouvre la boîte de dialogue (Modal) pour l'utilisateur
        await interaction.response.send_modal(EmailModal())

# --- Événements du Bot ---

@client.event
async def on_ready():
    """S'exécute quand le bot est connecté et prêt."""
    # Enregistre la vue persistante
    client.add_view(AdminPanelView())
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('Le bot est prêt et la vue persistante est enregistrée.')
    print('------')

@client.event
async def on_message(message):
    """S'exécute à chaque message reçu."""
    
    if message.author == client.user:
        return

    # Commande de test
    if message.content == '!ping':
        await message.channel.send('Pong !')

    # Commande pour poster le panneau d'administration (réservé aux admins)
    if message.content == '!setup_panel':
        if not message.author.guild_permissions.administrator:
            await message.channel.send("Vous n'avez pas la permission de faire ça.", delete_after=10)
            return
            
        # Créer le "panneau" (un Embed)
        embed = discord.Embed(
            title="Panneau d'administration - Sécrétaire TransFond",
            description="Utilisez le bouton ci-dessous pour gérer les accès au Google Sheet.",
            color=discord.Color.blue()
        )
        
        # Envoyer l'embed avec la vue (le bouton)
        await message.channel.send(embed=embed, view=AdminPanelView())

# --- Lancement ---
client.run(TOKEN)
