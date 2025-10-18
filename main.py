import os
import discord
import json
from discord.ui import Button, View, Modal, TextInput, Select
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build, HttpError

# --- Chargement des variables d'environnement ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GOOGLE_CREDS_JSON_STR = os.getenv('GOOGLE_CREDS_JSON')
GOOGLE_SHEET_ID_TRAVAIL = os.getenv('GOOGLE_SHEET_ID_TRAVAIL')
GOOGLE_SHEET_ID_DIRECTION = os.getenv('GOOGLE_SHEET_ID_DIRECTION')

# --- ID des salons pour les panneaux ---
ADMIN_CHANNEL_ID_ADD = 1429100071789793371      # Salon pour le panneau "Ajouter"
ADMIN_CHANNEL_ID_DELETE = 1429117305467437156  # Salon pour le panneau "Supprimer"
ADMIN_CHANNEL_ID_COPY = 1429100025530683392    # Salon pour le panneau "Copier"

# --- Vérification des variables ---
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
    try:
        creds_info = json.loads(GOOGLE_CREDS_JSON_STR)
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=creds)
        return drive_service
    except Exception as e:
        print(f"Erreur lors de l'authentification Google : {e}")
        return None

# ===================================================================
# --- SECTION 1 : LOGIQUE D'AJOUT D'ÉDITEUR ---
# ===================================================================

class AddEmailModal(Modal):
    def __init__(self, sheet_id: str, sheet_name: str):
        super().__init__(title=f'Ajouter - {sheet_name}')
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name
    
    email_input = TextInput(label='Adresse email à ajouter', placeholder='exemple@gmail.com', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        email = self.email_input.value
        await interaction.response.defer(ephemeral=True, thinking=True)
        drive_service = get_google_services()
        if not drive_service:
            await interaction.followup.send("Erreur: Connexion aux services Google impossible.", ephemeral=True)
            return
        try:
            permission = {'type': 'user', 'role': 'writer', 'emailAddress': email}
            drive_service.permissions().create(
                fileId=self.sheet_id, body=permission, sendNotificationEmail=True
            ).execute()
            await interaction.followup.send(f"Succès ! Accès éditeur à **{self.sheet_name}** donné à `{email}`.", ephemeral=True)
        except HttpError as error:
            await interaction.followup.send(f"Erreur : Impossible de partager. L'email est-il correct ?\n`{error}`", ephemeral=True)

class AdminAddView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Fiche de Travail', style=discord.ButtonStyle.success, custom_id='add_editor_travail')
    async def add_travail_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AddEmailModal(sheet_id=GOOGLE_SHEET_ID_TRAVAIL, sheet_name="Fiche de Travail"))

    @discord.ui.button(label='Direction', style=discord.ButtonStyle.primary, custom_id='add_editor_direction')
    async def add_direction_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(AddEmailModal(sheet_id=GOOGLE_SHEET_ID_DIRECTION, sheet_name="Direction"))

# ===================================================================
# --- SECTION 2 : LOGIQUE DE SUPPRESSION D'ÉDITEUR ---
# ===================================================================

class EditorSelectDropdown(Select):
    def __init__(self, sheet_id: str, sheet_name: str, editors: list):
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name
        options = [discord.SelectOption(label=editor['emailAddress'], value=editor['id']) for editor in editors]
        if not options:
             options.append(discord.SelectOption(label="Aucun éditeur trouvé", value="none", default=True))
        super().__init__(placeholder='Choisir l\'éditeur à supprimer...', min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        permission_id = self.values[0]
        if permission_id == "none":
            await interaction.response.edit_message(content="Aucune action effectuée.", view=None)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        drive_service = get_google_services()
        if not drive_service:
            await interaction.followup.send("Erreur: Connexion aux services Google impossible.", ephemeral=True)
            return
        try:
            permission = drive_service.permissions().get(fileId=self.sheet_id, permissionId=permission_id, fields='emailAddress').execute()
            email = permission.get('emailAddress', 'Inconnu')
            drive_service.permissions().delete(fileId=self.sheet_id, permissionId=permission_id).execute()
            await interaction.followup.send(f"Succès ! L'accès éditeur à **{self.sheet_name}** a été retiré à `{email}`.", ephemeral=True)
            await interaction.edit_original_response(content=f"L'utilisateur `{email}` a été supprimé.", view=None)
        except HttpError as error:
            await interaction.followup.send(f"Erreur lors de la suppression : \n`{error}`", ephemeral=True)

class AdminDeleteView(View):
    def __init__(self):
        super().__init__(timeout=None)

    async def fetch_editors(self, interaction: discord.Interaction, sheet_id: str, sheet_name: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        drive_service = get_google_services()
        if not drive_service:
            await interaction.followup.send("Erreur: Connexion aux services Google impossible.", ephemeral=True)
            return
        try:
            permissions = drive_service.permissions().list(fileId=sheet_id, fields="permissions(id, emailAddress, role)").execute()
            editors = [p for p in permissions.get('permissions', []) if p['role'] == 'writer' and 'emailAddress' in p]
            if not editors:
                await interaction.followup.send("Aucun éditeur (en dehors du propriétaire) n'a été trouvé.", ephemeral=True)
                return
            dropdown_view = View()
            dropdown_view.add_item(EditorSelectDropdown(sheet_id, sheet_name, editors))
            await interaction.followup.send("Choisissez l'éditeur à supprimer :", view=dropdown_view, ephemeral=True)
        except HttpError as error:
            await interaction.followup.send(f"Erreur lors de la récupération des éditeurs : \n`{error}`", ephemeral=True)

    @discord.ui.button(label='Supprimer (Fiche de Travail)', style=discord.ButtonStyle.danger, custom_id='delete_editor_travail')
    async def delete_travail_button(self, interaction: discord.Interaction, button: Button):
        await self.fetch_editors(interaction, GOOGLE_SHEET_ID_TRAVAIL, "Fiche de Travail")

    @discord.ui.button(label='Supprimer (Direction)', style=discord.ButtonStyle.secondary, custom_id='delete_editor_direction')
    async def delete_direction_button(self, interaction: discord.Interaction, button: Button):
        await self.fetch_editors(interaction, GOOGLE_SHEET_ID_DIRECTION, "Direction")

# ===================================================================
# --- SECTION 3 : LOGIQUE DE COPIE DE DOCUMENT --- (NOUVEAU)
# ===================================================================

class CopySheetModal(Modal):
    """Boîte de dialogue pour demander le nom de la nouvelle copie."""
    def __init__(self, sheet_id: str, sheet_name: str):
        super().__init__(title='Créer une copie')
        self.sheet_id = sheet_id
        self.sheet_name = sheet_name

        self.file_name_input = TextInput(
            label='Nom de la nouvelle copie',
            placeholder=f'Copie de {self.sheet_name}',
            required=True
        )
        self.add_item(self.file_name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.file_name_input.value
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        drive_service = get_google_services()
        if not drive_service:
            await interaction.followup.send("Erreur: Connexion aux services Google impossible.", ephemeral=True)
            return
        try:
            # Définir les métadonnées (juste le nom) pour la copie
            file_metadata = {'name': new_name}
            
            # Appeler l'API Google Drive pour copier le fichier
            copied_file = drive_service.files().copy(
                fileId=self.sheet_id,
                body=file_metadata,
                fields='id, name, webViewLink'  # Demander à l'API de retourner ces infos
            ).execute()

            file_name = copied_file.get('name')
            file_link = copied_file.get('webViewLink')

            await interaction.followup.send(f"Succès ! Copie créée : **[{file_name}]({file_link})**\n*La copie se trouve dans le même dossier que l'original.*", ephemeral=True)
        
        except HttpError as error:
            await interaction.followup.send(f"Erreur lors de la copie : \n`{error}`", ephemeral=True)

class AdminCopyView(View):
    """La vue persistante avec le bouton 'Copier'."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='Créer une copie (Fiche de Travail)', style=discord.ButtonStyle.blurple, custom_id='copy_doc_travail', emoji='📄')
    async def copy_travail_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(
            CopySheetModal(sheet_id=GOOGLE_SHEET_ID_TRAVAIL, sheet_name="Fiche de Travail")
        )

# ===================================================================
# --- SECTION 4 : ÉVÉNEMENTS DU BOT (ON_READY) --- (MIS À JOUR)
# ===================================================================

async def setup_panel(channel_id: int, embed: discord.Embed, view: View):
    """Fonction générique pour créer ou mettre à jour un panneau."""
    try:
        channel = await client.fetch_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            print(f"Erreur : Salon introuvable ou n'est pas un salon textuel (ID: {channel_id}).")
            return
        panel_message = None
        async for message in channel.history(limit=50):
            if message.author == client.user and message.embeds and message.embeds[0].title == embed.title:
                panel_message = message
                break
        if panel_message:
            await panel_message.edit(embed=embed, view=view)
            print(f"Panneau '{embed.title}' mis à jour dans #{channel.name}.")
        else:
            await channel.send(embed=embed, view=view)
            print(f"Panneau '{embed.title}' créé dans #{channel.name}.")
    except discord.errors.Forbidden:
        print(f"Erreur : Permissions manquantes pour lire/écrire dans le salon {channel_id}.")
    except Exception as e:
        print(f"Erreur inattendue lors du setup du panneau {channel_id} : {e}")

@client.event
async def on_ready():
    """S'exécute quand le bot est connecté et prêt."""
    
    # ÉTAPE 1 : Enregistrer TOUTES les vues persistantes
    client.add_view(AdminAddView())
    client.add_view(AdminDeleteView())
    client.add_view(AdminCopyView()) # NOUVEAU
    
    print(f'Connecté en tant que {client.user} (ID: {client.user.id})')
    print('------')

    # ÉTAPE 2 : Mettre à jour le panneau d'AJOUT
    add_embed = discord.Embed(title="Panneau d'administration - AJOUT", description="Utilisez les boutons ci-dessous pour **ajouter** un accès éditeur.", color=discord.Color.blue())
    add_embed.add_field(name="Fiche de Travail", value="Donne l'accès éditeur au document principal.", inline=False)
    add_embed.add_field(name="Direction", value="Donne l'accès éditeur au document de la direction.", inline=False)
    await setup_panel(ADMIN_CHANNEL_ID_ADD, add_embed, AdminAddView())

    # ÉTAPE 3 : Mettre à jour le panneau de SUPPRESSION
    delete_embed = discord.Embed(title="Panneau d'administration - SUPPRESSION", description="Utilisez les boutons ci-dessous pour **supprimer** un accès éditeur.", color=discord.Color.red())
    delete_embed.add_field(name="Fiche de Travail", value="Liste les éditeurs et permet la suppression.", inline=False)
    delete_embed.add_field(name="Direction", value="Liste les éditeurs et permet la suppression.", inline=False)
    await setup_panel(ADMIN_CHANNEL_ID_DELETE, delete_embed, AdminDeleteView())

    # ÉTAPE 4 : Mettre à jour le panneau de COPIE (NOUVEAU)
    copy_embed = discord.Embed(title="Panneau d'administration - COPIE", description="Utilisez ce bouton pour créer une copie d'un document.", color=discord.Color.gold()) # Couleur 'Or'
    copy_embed.add_field(name="Fiche de Travail", value="Crée une nouvelle copie du document de travail.", inline=False)
    await setup_panel(ADMIN_CHANNEL_ID_COPY, copy_embed, AdminCopyView())

@client.event
async def on_message(message):
    """Gère les commandes manuelles (ex: !ping)."""
    if message.author == client.user: return
    if message.content == '!ping':
        await message.channel.send('Pong !')

# --- Lancement ---
client.run(TOKEN)
