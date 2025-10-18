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
GOOGLE_CREDS_JSON_STR = os.getenv('GOOGLE_CREDS_JSON')

# --- Charger les IDs des deux Google Sheets ---
GOOGLE_SHEET_ID_TRAVAIL = os.getenv('GOOGLE_SHEET_ID_TRAVAIL')
GOOGLE_SHEET_ID_DIRECTION = os.getenv('GOOGLE_SHEET_ID_DIRECTION')

# --- ID du salon pour le panneau d'administration ---
ADMIN_CHANNEL_ID = 1429100071789793371 # L'ID de votre salon

# Vérifier si les variables critiques sont chargées
if not all([TOKEN, GOOGLE_CREDS_JSON_STR, GOOGLE_SHEET_ID_TRAVAIL, GOOGLE_SHEET_ID_DIRECTION]):
    print("ERREUR CRITIQUE : Variables d'environnement manquantes.")
    print("Vérifiez DISCORD_TOKEN, GOOGLE_CREDS_JSON, GOOGLE_SHEET_ID_TRAVAIL, et GOOGLE_SHEET_ID_DIRECTION sur Railway.")
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
# Elle accepte maintenant un sheet_id pour savoir quel document partager
class EmailModal(Modal):
    
    def __init__(self, sheet_id: str, sheet_name: str):
        super().__init__(title=f'Partage - {sheet_name}')
        self.sheet_id = sheet_id # Stocke l'ID du sheet à partager
        self.sheet_name = sheet_name

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
                fileId=self.sheet_id,  # Utilise l'ID stocké
                body=permission,
                sendNotificationEmail=True
            ).execute()
            
            await interaction.followup.send(f"Succès ! L'accès éditeur à **{self.sheet_name}** a été donné à `{email}`.", ephemeral=True)
            
        except HttpError as error:
            print(f"Erreur API Google : {error}")
            await interaction.followup.send(f"Erreur : Impossible de partager le document. L'email est-il correct ?\n`{error}`", ephemeral=True)
        except Exception as e:
            print(f"Erreur inattendue : {e}")
            await interaction.followup.send(f"Une erreur inconnue est survenue : `{e}`", ephemeral=True)

# --- Vue persistante avec les DEUX boutons ---
class AdminPanelView(View):
    def __init__(self):
        super().__init__(timeout=None) # Vue persistante

    @discord.ui.button(label='Fiche de Travail', style=discord.ButtonStyle.success, custom_id='add_editor_travail')
    async def add_editor_travail_button(self, interaction: discord.Interaction, button: Button):
        """Ouvre le modal pour le sheet 'Fiche de Travail'."""
        # Récupère l'ID depuis les variables d'environnement
        sheet_id = os.getenv('GOOGLE_SHEET_ID_TRAVAIL')
        await interaction.response.send_modal(EmailModal(sheet_id=sheet_id, sheet_name="Fiche de Travail"))

    @discord.ui.button(label='Direction', style=discord.ButtonStyle.primary, custom_id='add_editor_direction')
    async def add_editor_direction_button(self, interaction: discord.Interaction, button: Button):
        """Ouvre le modal pour le sheet 'Direction'."""
        # Récupère l'ID depuis les variables d'environnement
        sheet_id = os.getenv('GOOGLE_SHEET_ID_DIRECTION')
        await interaction.response.send_modal(EmailModal(sheet_id=sheet_id, sheet_name="Direction"))

# --- Événements du Bot ---

@client.event
async def on_ready():
    """S'exécute quand le bot est connecté et prêt."""
    
    # ÉTAPE 1 : Enregistrer la vue persistante
    client.add_view(AdminPanelView())
    
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('------')
    print(f"Recherche du panneau d'administration dans le salon {ADMIN_CHANNEL_ID}...")

    # ÉTAPE 2 : Définir le contenu du panneau (mis à jour)
    embed = discord.Embed(
        title="Panneau d'administration - Sécrétaire TransFond",
        description="Utilisez les boutons ci-dessous pour gérer les accès aux Google Sheets.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Fiche de Travail", value="Donne l'accès éditeur au document principal.", inline=False)
    embed.add_field(name="Direction", value="Donne l'accès éditeur au document de la direction.", inline=False)
    
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
            if message.author == client.user and message.embeds and message.embeds[0].title == embed.title:
                panel_message = message
                break
        
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
            description="Utilisez les boutons ci-dessous pour gérer les accès aux Google Sheets.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Fiche de Travail", value="Donne l'accès éditeur au document principal.", inline=False)
        embed.add_field(name="Direction", value="Donne l'accès éditeur au document de la direction.", inline=False)
        
        await message.channel.send(embed=embed, view=AdminPanelView())
        await message.delete()

# --- Lancement ---
client.run(TOKEN)
