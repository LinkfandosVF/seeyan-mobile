#!/usr/bin/env python3
"""
Seeyah - Social Media iOS App (Toga / BeeWare)
================================================
A single-file iOS app built with Toga that mirrors the functionality
of the Seeyah PHP social-media platform.

Features:
  - Login / 2FA / Register
  - Feed with pagination (load 5 posts at a time, tap "Load More")
  - Deferred avatar loading (text renders instantly, avatars load in background)
  - Lazy image loading (tap to view, never pre-fetched)
  - Tappable @usernames to view profiles
  - Post images with fullscreen viewer
  - Search (posts + hashtags)
  - Messages (server-loaded conversations & chat history)
  - Notifications (server-loaded)
  - Bottom tab bar (iOS/Android feel)
  - No horizontal overflow (everything wraps to screen width)

Requirements:
    pip install toga httpx

Valid Toga Pack properties (ONLY these may be used):
    direction, alignment, flex, padding/padding_top/padding_bottom/padding_left/padding_right,
    margin/margin_top/margin_bottom/margin_left/margin_right,
    width, height, min_width, min_height, max_width, max_width
"""

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW, CENTER
import httpx
import threading
import re
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_URL = "https://seeyan.duckdns.org"
PAGE_SIZE = 5  # posts per page

app_state = {
    "username": None,
    "session_cookie": None,
    "current_tab": "feed",
    "viewing_profile": None,
}

NOTIF_ICONS = {
    "follow": "FOLLOW",
    "like": "LIKE",
    "comment": "COMMENT",
    "repost": "REPOST",
    "admin": "ADMIN",
    "mention": "MENTION",
}


# ===========================================================================
# API Helper
# ===========================================================================
class SeeyahAPI:
    """Thin wrapper around the Seeyah PHP backend."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=15.0)
        self._avatar_cache = {}

    # ---- Auth ----

    def login(self, username: str, password: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "login", "username": username, "password": password},
            follow_redirects=True,
        )
        for cookie in r.cookies.jar:
            if cookie.name == "PHPSESSID":
                app_state["session_cookie"] = cookie.value
        return r

    def verify_2fa(self, code: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "verify_2fa", "code": code},
            follow_redirects=True,
        )
        return r

    def register(self, username: str, password: str, display_name: str = ""):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={
                "action": "register",
                "username": username,
                "password": password,
                "display_name": display_name or username,
            },
            follow_redirects=True,
        )
        return r

    def logout(self):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "logout"},
            follow_redirects=True,
        )
        app_state["username"] = None
        app_state["session_cookie"] = None
        return r

    # ---- Posts ----

    def get_posts(self):
        r = self.client.get(f"{self.base_url}/api_posts.php")
        if r.status_code == 200:
            data = r.json()
            return data.get("posts", [])
        return []

    def create_post(self, content: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "post", "content": content},
            follow_redirects=True,
        )
        return r

    def delete_post(self, post_id: str, delete_type: str = "soft"):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "delete_post", "post_id": post_id, "delete_type": delete_type},
            follow_redirects=True,
        )
        return r

    def toggle_like(self, post_id: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "toggle_like", "post_id": post_id},
        )
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"success": False}
        return {"success": False}

    def repost(self, post_id: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "repost", "post_id": post_id},
            follow_redirects=True,
        )
        return r

    def add_comment(self, post_id: str, content: str, reply_to: str = ""):
        data = {"action": "comment", "post_id": post_id, "content": content}
        if reply_to:
            data["reply_to"] = reply_to
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data=data,
            follow_redirects=True,
        )
        return r

    # ---- Social ----

    def follow(self, target_user: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "follow", "target_user": target_user},
            follow_redirects=True,
        )
        return r

    def unfollow(self, target_user: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "unfollow", "target_user": target_user},
            follow_redirects=True,
        )
        return r

    def block(self, target_user: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "block", "target_user": target_user},
            follow_redirects=True,
        )
        return r

    def unblock(self, target_user: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "unblock", "target_user": target_user},
            follow_redirects=True,
        )
        return r

    def follow_tag(self, tag: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "follow_tag", "tag": tag},
            follow_redirects=True,
        )
        return r

    def unfollow_tag(self, tag: str):
        r = self.client.post(
            f"{self.base_url}/engine.php",
            data={"action": "unfollow_tag", "tag": tag},
            follow_redirects=True,
        )
        return r

    # ---- Messages (server-loaded) ----

    def send_message(self, to_user: str, message: str, reply_to: str = ""):
        data = {"action": "send_message_ajax", "to": to_user, "message": message}
        if reply_to:
            data["reply_to"] = reply_to
        r = self.client.post(f"{self.base_url}/messages.php", data=data)
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return {"success": False}
        return {"success": False}

    def get_conversations(self):
        """Parse conversation list from messages.php HTML."""
        try:
            r = self.client.get(f"{self.base_url}/messages.php", follow_redirects=True)
            if r.status_code != 200:
                return []
            convs = []
            pattern = (
                r'<a href="\?conv=([^"]+)"[^>]*class="conv-item[^"]*"[^>]*>.*?'
                r'<div class="conv-name">@([^<]+)</div>.*?'
                r'<div class="conv-preview">([^<]*)</div>'
            )
            for m in re.finditer(pattern, r.text, re.DOTALL):
                convs.append({
                    "conv_id": m.group(1),
                    "with": m.group(2).strip(),
                    "last_message": m.group(3).strip(),
                })
            return convs
        except Exception:
            return []

    def start_conversation(self, username: str):
        """Start or get conversation with a user. Returns conv_id or None."""
        try:
            r = self.client.get(
                f"{self.base_url}/messages.php",
                params={"with": username},
                follow_redirects=True,
            )
            if r.status_code != 200:
                return None
            m = re.search(r"const convId = '([^']+)'", r.text)
            if m:
                return m.group(1)
            m = re.search(r'<a href="\?conv=([^"]+)" class="conv-item active"', r.text)
            if m:
                return m.group(1)
            return None
        except Exception:
            return None

    def get_messages(self, conv_id: str):
        """Fetch messages for a conversation via AJAX endpoint."""
        try:
            r = self.client.get(
                f"{self.base_url}/messages.php",
                params={"ajax": "1", "conv": conv_id},
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"messages": [], "time": 0}

    # ---- Notifications ----

    def get_notifications(self):
        """Fetch notifications via AJAX endpoint."""
        try:
            r = self.client.get(
                f"{self.base_url}/notifications.php",
                params={"ajax": "1"},
            )
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
        return {"count": 0, "notifications": []}

    def mark_notifications_read(self):
        """Mark all notifications as read."""
        try:
            self.client.post(
                f"{self.base_url}/engine.php",
                data={"action": "mark_read"},
                follow_redirects=True,
            )
        except Exception:
            pass

    # ---- Profile ----

    def get_profile(self, username: str):
        """Fetch user profile info by parsing profile.php HTML."""
        try:
            r = self.client.get(
                f"{self.base_url}/profile.php",
                params={"user": username},
                follow_redirects=True,
            )
            if r.status_code != 200:
                return None
            html = r.text
            display_name = username
            bio = ""
            followers = 0
            following = 0
            member_since = ""
            is_following = False

            m = re.search(r"<h1>([^<]+)</h1>", html)
            if m:
                display_name = m.group(1).strip()

            m = re.search(r'<div class="bio">([^<]+)</div>', html)
            if m:
                bio = m.group(1).strip()

            for m in re.finditer(
                r'<div class="follow-stat">\s*<strong>(\d+)</strong>\s*(\w+)', html
            ):
                count = int(m.group(1))
                label = m.group(2)
                if "follower" in label and "followi" not in label:
                    followers = count
                elif "following" in label:
                    following = count

            m = re.search(r'class="stat-number"[^>]*>(\d{4})', html)
            if m:
                member_since = m.group(1)

            is_following = bool(re.search(r'class="follow-btn following"', html))

            return {
                "display_name": display_name,
                "bio": bio,
                "followers": followers,
                "following": following,
                "member_since": member_since,
                "is_following": is_following,
            }
        except Exception:
            return None

    # ---- Media ----

    def fetch_avatar(self, username: str):
        """Fetch and cache a user's avatar image from their profile page."""
        if not username or username == "[deleted]":
            return None
        if username in self._avatar_cache:
            return self._avatar_cache[username]
        data = self._do_fetch_avatar(username)
        self._avatar_cache[username] = data
        return data

    def _do_fetch_avatar(self, username: str):
        try:
            r = self.client.get(
                f"{self.base_url}/profile.php",
                params={"user": username},
                follow_redirects=True,
            )
            if r.status_code != 200:
                return None
            m = re.search(r'<img src="(data/avatars/[^"]+)"', r.text)
            if m:
                avatar_url = m.group(1)
                if not avatar_url.startswith("http"):
                    avatar_url = f"{self.base_url}/{avatar_url}"
                r2 = self.client.get(avatar_url, follow_redirects=True, timeout=5.0)
                if r2.status_code == 200 and r2.content and len(r2.content) > 100:
                    return r2.content
        except Exception:
            pass
        return None

    def fetch_post_image(self, image_filename: str):
        """Fetch a post image by filename. Returns bytes or None."""
        if not image_filename:
            return None
        try:
            url = f"{self.base_url}/data/post-images/{image_filename}"
            r = self.client.get(url, follow_redirects=True, timeout=10.0)
            if r.status_code == 200 and r.content and len(r.content) > 100:
                return r.content
        except Exception:
            pass
        return None


api = SeeyahAPI(BASE_URL)


# ===========================================================================
# Seeyah App
# ===========================================================================
class SeeyahApp(toga.App):
    """Main application class for the Seeyah social media iOS app."""

    def startup(self):
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.root_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
        self.main_window.content = self.root_box
        self.show_login_screen()
        self.main_window.show()

    # ========================================================================
    # Screen helpers
    # ========================================================================
    def _clear(self):
        for child in list(self.root_box.children):
            self.root_box.remove(child)

    def _run_in_thread(self, target, *args):
        """Run a function in a background thread."""
        threading.Thread(target=target, args=args, daemon=True).start()

    def _on_main_thread(self, func, *args):
        """Schedule a function call on the main thread."""
        self.loop.call_soon_threadsafe(func, *args)

    # ========================================================================
    # LOGIN SCREEN
    # ========================================================================
    def show_login_screen(self, widget=None):
        self._clear()

        box = toga.Box(style=Pack(direction=COLUMN, flex=1, alignment=CENTER, padding=30))

        box.add(toga.Label("Seeyah", style=Pack(margin_bottom=5, alignment=CENTER)))
        box.add(toga.Label("Welcome back!", style=Pack(margin_bottom=20, alignment=CENTER)))

        box.add(toga.Label("Username", style=Pack(margin_bottom=2)))
        self.login_username = toga.TextInput(placeholder="your_username", style=Pack(margin_bottom=8))
        box.add(self.login_username)

        box.add(toga.Label("Password", style=Pack(margin_bottom=2)))
        self.login_password = toga.PasswordInput(placeholder="Password", style=Pack(margin_bottom=12))
        box.add(self.login_password)

        login_btn = toga.Button("Log in", on_press=self._handle_login, style=Pack(margin_bottom=10))
        box.add(login_btn)

        self.twofa_box = toga.Box(style=Pack(direction=COLUMN, margin_top=10))
        self.login_error = toga.Label("", style=Pack(margin_top=8))
        box.add(self.login_error)

        register_btn = toga.Button("Sign up", on_press=self.show_register_screen, style=Pack(margin_top=12))
        box.add(register_btn)

        server_box = toga.Box(style=Pack(direction=ROW, margin_top=20))
        server_box.add(toga.Label("Server: ", style=Pack(margin_right=5)))
        self.server_url_input = toga.TextInput(style=Pack(flex=1))
        self.server_url_input.value = BASE_URL
        server_box.add(self.server_url_input)
        box.add(server_box)

        box.add(self.twofa_box)
        self.root_box.add(box)

    def _show_2fa_form(self):
        for child in list(self.twofa_box.children):
            self.twofa_box.remove(child)
        self.twofa_box.add(toga.Label("2FA: Enter 6-digit code", style=Pack(margin_bottom=5)))
        self.twofa_code = toga.TextInput(placeholder="000000", style=Pack(margin_bottom=5))
        self.twofa_box.add(self.twofa_code)
        self.twofa_box.add(toga.Button("Verify", on_press=self._handle_2fa, style=Pack(margin_bottom=5)))

    # ========================================================================
    # REGISTER SCREEN
    # ========================================================================
    def show_register_screen(self, widget=None):
        self._clear()

        box = toga.Box(style=Pack(direction=COLUMN, flex=1, alignment=CENTER, padding=30))

        box.add(toga.Label("Create Account", style=Pack(margin_bottom=20, alignment=CENTER)))

        box.add(toga.Label("Username", style=Pack(margin_bottom=2)))
        self.reg_username = toga.TextInput(placeholder="Username", style=Pack(margin_bottom=8))
        box.add(self.reg_username)

        box.add(toga.Label("Display Name", style=Pack(margin_bottom=2)))
        self.reg_display = toga.TextInput(placeholder="Display name", style=Pack(margin_bottom=8))
        box.add(self.reg_display)

        box.add(toga.Label("Password", style=Pack(margin_bottom=2)))
        self.reg_password = toga.PasswordInput(placeholder="Password", style=Pack(margin_bottom=12))
        box.add(self.reg_password)

        box.add(toga.Button("Sign up", on_press=self._handle_register, style=Pack(margin_bottom=8)))
        box.add(toga.Button("Back to Login", on_press=self.show_login_screen, style=Pack(margin_bottom=8)))

        self.reg_error = toga.Label("", style=Pack(margin_top=8))
        box.add(self.reg_error)

        self.root_box.add(box)

    # ========================================================================
    # MAIN APP - Bottom Tab Bar Layout
    # ========================================================================


    def show_main_app(self, widget=None):
        self._clear()
        app_state["viewing_profile"] = None

        # État du flux pour la pagination
        self._all_posts = []
        self._displayed_count = 0
        self._avatar_cache = {}
        self._feed_ready = False

        # Barre de navigation native
        self.commands.clear()
        logout_cmd = toga.Command(
            self._handle_logout,
            text="Déconnexion",
            group=toga.Group.COMMANDS
        )
        self.commands.add(logout_cmd)

        # 1. Préparation des conteneurs pour chaque onglet
        # On utilise 'margin' à la place de 'padding' pour éviter les warnings
        self.feed_area = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self.search_area = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self.notif_area = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self.msg_area = toga.Box(style=Pack(direction=COLUMN, margin=10))
        self.profile_area = toga.Box(style=Pack(direction=COLUMN, margin=10))

        # 2. Utilisation de l'OptionContainer (le widget d'onglets natif de l'OS)
        self.main_tabs = toga.OptionContainer(
            content=[
                ("Feed", toga.ScrollContainer(content=self.feed_area)),
                ("Search", toga.ScrollContainer(content=self.search_area)),
                ("Notifs", toga.ScrollContainer(content=self.notif_area)),
                ("Msgs", toga.ScrollContainer(content=self.msg_area)),
                ("Me", toga.ScrollContainer(content=self.profile_area)),
            ],
            style=Pack(flex=1),
            on_select=self._on_tab_selected
        )

        self.root_box.add(self.main_tabs)

        # 3. Initialisation du premier onglet
        self.content_area = self.feed_area 
        self._load_feed_tab()

    def _on_tab_selected(self, widget):
        """Gère le changement d'onglet natif (doit être indentée dans la classe)."""
        tab_map = ["feed", "search", "notifications", "messages", "profile"]
        selected_index = widget.current_tab.index
        
        areas = [self.feed_area, self.search_area, self.notif_area, self.msg_area, self.profile_area]
        self.content_area = areas[selected_index]
        
        self._switch_tab(tab_map[selected_index])





    # ========================================================================
    # Tab Switching
    # ========================================================================
    def _switch_tab(self, tab_name: str):
        app_state["current_tab"] = tab_name
        app_state["viewing_profile"] = None

        # Clear only the content area, not the nav or tab bar
        for child in list(self.content_area.children):
            self.content_area.remove(child)

        if tab_name == "feed":
            self._load_feed_tab()
        elif tab_name == "search":
            self._load_search_tab()
        elif tab_name == "profile":
            self._load_profile_tab(app_state["username"])
        elif tab_name == "messages":
            self._load_messages_tab()
        elif tab_name == "notifications":
            self._load_notifications_tab()

    # ========================================================================
    # FEED TAB - Paginated + Deferred Avatar Loading
    # ========================================================================
    def _load_feed_tab(self):
        self.content_area.add(
            toga.Button("Refresh", on_press=lambda w: self._refresh_feed(), style=Pack(margin_bottom=8))
        )

        # Composer
        composer = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10, padding=8))
        composer.add(toga.Label("What's on your mind?", style=Pack(margin_bottom=5)))
        self.composer_input = toga.MultilineTextInput(
            placeholder="Write a post...",
            style=Pack(height=80, margin_bottom=5),
        )
        composer.add(self.composer_input)
        composer.add(toga.Button("Publish", on_press=self._handle_create_post, style=Pack(margin_bottom=5)))
        self.content_area.add(composer)

        self.feed_loading = toga.Label("Loading posts...", style=Pack(margin_bottom=5))
        self.content_area.add(self.feed_loading)

        self._run_in_thread(self._fetch_posts)

    def _refresh_feed(self):
        """Full refresh of the feed."""
        self._all_posts = []
        self._displayed_count = 0
        self._avatar_cache = {}
        self._feed_ready = False

        for child in list(self.content_area.children):
            self.content_area.remove(child)

        self.content_area.add(
            toga.Button("Refresh", on_press=lambda w: self._refresh_feed(), style=Pack(margin_bottom=8))
        )

        composer = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10, padding=8))
        composer.add(toga.Label("What's on your mind?", style=Pack(margin_bottom=5)))
        self.composer_input = toga.MultilineTextInput(
            placeholder="Write a post...",
            style=Pack(height=80, margin_bottom=5),
        )
        composer.add(self.composer_input)
        composer.add(toga.Button("Publish", on_press=self._handle_create_post, style=Pack(margin_bottom=5)))
        self.content_area.add(composer)

        self.feed_loading = toga.Label("Loading posts...", style=Pack(margin_bottom=5))
        self.content_area.add(self.feed_loading)

        self._run_in_thread(self._fetch_posts)

    def _fetch_posts(self):
        """Fetch JSON once, sort, then render first page immediately."""
        try:
            posts = api.get_posts()
            posts.sort(key=lambda p: int(p.get("created_at", 0)), reverse=True)
            self._all_posts = posts
            self._on_main_thread(self._render_feed_page)
        except Exception as e:
            self._on_main_thread(self._set_label_text, self.feed_loading, f"Error: {e}")

    def _render_feed_page(self):
        """Render the next PAGE_SIZE posts. Shows text immediately, avatars later."""
        if self.feed_loading in self.content_area.children:
            self.content_area.remove(self.feed_loading)

        start = self._displayed_count
        end = min(start + PAGE_SIZE, len(self._all_posts))

        if start >= len(self._all_posts):
            if self._displayed_count == 0:
                self.content_area.add(toga.Label("No posts yet. Be the first!", style=Pack(margin_top=10)))
            return

        # Remove the old "Load More" button if it exists
        for child in list(self.content_area.children):
            if isinstance(child, toga.Button) and hasattr(child, '_is_load_more'):
                self.content_area.remove(child)
                break

        # Render posts as text-only cards (FAST - no network calls)
        for i in range(start, end):
            post = self._all_posts[i]
            self.content_area.add(self._build_post_card(post))

        self._displayed_count = end

        # "Load More" button if there are more posts
        if end < len(self._all_posts):
            remaining = len(self._all_posts) - end
            load_more_btn = toga.Button(
                f"Load More ({remaining} remaining)",
                on_press=lambda w: self._render_feed_page(),
                style=Pack(margin_top=10, margin_bottom=10),
            )
            load_more_btn._is_load_more = True
            self.content_area.add(load_more_btn)

        # NOW fetch avatars in background (non-blocking, updates cards when ready)
        self._run_in_thread(self._fetch_avatars_for_displayed_posts)

    def _fetch_avatars_for_displayed_posts(self):
        """Fetch avatars only for currently displayed posts, then update UI."""
        try:
            end = min(self._displayed_count, len(self._all_posts))
            unique_authors = set()
            for i in range(end):
                author = self._all_posts[i].get("author")
                if author and author not in self._avatar_cache and author != "[deleted]":
                    unique_authors.add(author)

            for author in unique_authors:
                data = api.fetch_avatar(author)
                self._avatar_cache[author] = data

            # Rebuild the visible cards with avatar data
            self._on_main_thread(self._rebuild_feed_with_avatars)
        except Exception:
            pass

    def _rebuild_feed_with_avatars(self):
        """Remove old text-only cards and rebuild with avatars."""
        # Find the index of the first post card (after composer + refresh button)
        # We need to preserve: [refresh btn, composer box, ...post cards..., load more btn]
        card_indices = []
        children = list(self.content_area.children)
        for i, child in enumerate(children):
            if isinstance(child, toga.Box) and hasattr(child, '_is_post_card'):
                card_indices.append(i)

        if not card_indices:
            return

        # Replace each post card with a new one that has the avatar
        for idx in reversed(card_indices):
            child = children[idx]
            if hasattr(child, '_post_data'):
                post = child._post_data
                av = self._avatar_cache.get(post.get("author"))
                new_card = self._build_post_card(post, avatar_data=av)
                self.content_area.insert(idx, new_card)
                self.content_area.remove(child)

    def _build_post_card(self, post: dict, avatar_data=None) -> toga.Box:
        """Build a single post card. avatar_data=None means text-only (fast path)."""
        card = toga.Box(style=Pack(direction=COLUMN, padding=8, margin_bottom=8))
        card._is_post_card = True
        card._post_data = post

        author = post.get("author", "[deleted]")
        content = post.get("content", "")
        created_at = post.get("created_at", 0)
        post_id = post.get("id", "")
        is_repost = post.get("repost", False)
        repost_author = post.get("repost_author", "")
        comments = post.get("comments", [])
        has_image = bool(post.get("image", ""))

        try:
            dt = datetime.fromtimestamp(int(created_at))
            date_str = dt.strftime("%d %b %Y")
        except (ValueError, TypeError, OSError):
            date_str = "Unknown"

        # Header row
        header = toga.Box(style=Pack(direction=ROW, margin_bottom=3, alignment=CENTER))

        # Avatar placeholder or actual avatar
        if avatar_data:
            try:
                avatar_img = toga.Image(data=avatar_data)
                avatar_view = toga.ImageView(avatar_img, style=Pack(height=28, margin_right=6))
                header.add(avatar_view)
            except Exception:
                header.add(toga.Box(style=Pack(width=28, height=28, margin_right=6)))
        else:
            header.add(toga.Box(style=Pack(width=28, height=28, margin_right=6)))

        # Tappable @username
        header.add(
            toga.Button(
                f"@{author}",
                on_press=lambda w, a=author: self._view_profile(a),
                style=Pack(margin_right=8),
            )
        )
        header.add(toga.Label(date_str, style=Pack(flex=1)))
        card.add(header)

        # Repost indicator
        if is_repost:
            card.add(toga.Label(f"Reposted from @{repost_author}", style=Pack(margin_bottom=3)))

        # Post content - truncated in feed, tap to see full post detail
        if content:
            display_text = content
            if len(content) > 150:
                display_text = content[:147] + "..."
            card.add(
                toga.Button(
                    display_text,
                    on_press=lambda w, p=post: self._show_post_detail(p),
                    style=Pack(margin_bottom=5),
                )
            )

        # Image indicator (tap to load - lazy, not pre-fetched)
        if has_image:
            card.add(
                toga.Button(
                    "[View Image]",
                    on_press=lambda w, p=post: self._on_tap_post_image(p),
                    style=Pack(margin_bottom=5),
                )
            )

        # Actions row
        actions = toga.Box(style=Pack(direction=ROW, margin_bottom=3))

        like_count = post.get("like_count", 0)
        actions.add(
            toga.Button(
                f"Like ({like_count})",
                on_press=lambda w, pid=post_id: self._handle_like(pid),
                style=Pack(margin_right=5),
            )
        )
        actions.add(
            toga.Button(
                "Repost",
                on_press=lambda w, pid=post_id: self._handle_repost(pid),
                style=Pack(margin_right=5),
            )
        )
        actions.add(
            toga.Button(
                f"Comments ({len(comments)})",
                on_press=lambda w, p=post: self._show_post_detail(p),
                style=Pack(margin_right=5),
            )
        )

        if author == app_state.get("username"):
            actions.add(
                toga.Button(
                    "Delete",
                    on_press=lambda w, pid=post_id: self._handle_delete_post(pid),
                )
            )

        card.add(actions)

        # Comment previews (first 2, truncated to prevent overflow)
        for comment in comments[:2]:
            c_author = comment.get("author", "[deleted]")
            c_text = comment.get("content", "")
            if len(c_text) > 80:
                c_text = c_text[:77] + "..."
            c_box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=2, margin_left=15))
            c_box.add(toga.Label(f"@{c_author}:"))
            c_box.add(toga.Label(c_text))
            card.add(c_box)

        if len(comments) > 2:
            card.add(
                toga.Label(f"  +{len(comments) - 2} more...", style=Pack(margin_bottom=2, margin_left=15))
            )

        return card

    # ========================================================================
    # FULLSCREEN IMAGE VIEWER (lazy - only loads on tap)
    # ========================================================================
    def _on_tap_post_image(self, post: dict):
        img_file = post.get("image", "")
        if not img_file:
            return
        self._clear()

        box = toga.Box(style=Pack(direction=COLUMN, flex=1, padding=10, alignment=CENTER))
        box.add(toga.Button("X Close", on_press=self.show_main_app, style=Pack(margin_bottom=10)))
        box.add(toga.Label("Loading image...", style=Pack(margin_bottom=10)))

        scroll = toga.ScrollContainer(style=Pack(flex=1))
        self._img_viewer_content = toga.Box(style=Pack(direction=COLUMN, alignment=CENTER))
        scroll.content = self._img_viewer_content
        box.add(scroll)
        self.root_box.add(box)

        self._run_in_thread(self._do_load_fullscreen_image, img_file)

    def _do_load_fullscreen_image(self, image_filename: str):
        try:
            data = api.fetch_post_image(image_filename)
            self._on_main_thread(self._display_fullscreen_image, data)
        except Exception:
            self._on_main_thread(self._display_fullscreen_image, None)

    def _display_fullscreen_image(self, image_data):
        self._clear_children(self._img_viewer_content)
        if image_data:
            try:
                img = toga.Image(data=image_data)
                # Use flex=1 so the image scales to screen width, no overflow
                img_view = toga.ImageView(img, style=Pack(flex=1))
                self._img_viewer_content.add(img_view)
            except Exception:
                self._img_viewer_content.add(toga.Label("Could not display image."))
        else:
            self._img_viewer_content.add(toga.Label("Failed to load image."))

    # ========================================================================
    # POST DETAIL
    # ========================================================================
    def _show_post_detail(self, post: dict):
        self._clear()

        author = post.get("author", "[deleted]")
        post_id = post.get("id", "")
        content = post.get("content", "")
        created_at = post.get("created_at", 0)
        comments = post.get("comments", [])
        avatar_data = self._avatar_cache.get(author)

        try:
            dt = datetime.fromtimestamp(int(created_at))
            date_str = dt.strftime("%d %b %Y")
        except (ValueError, TypeError, OSError):
            date_str = "Unknown"

        # Everything inside one scroll container (handles long content + keyboard)
        inner = toga.Box(style=Pack(direction=COLUMN, padding=10))

        inner.add(toga.Button("Back", on_press=self.show_main_app, style=Pack(margin_bottom=10)))

        # Header with big avatar
        header = toga.Box(style=Pack(direction=ROW, alignment=CENTER, margin_bottom=8))
        if avatar_data:
            try:
                avatar_img = toga.Image(data=avatar_data)
                avatar_view = toga.ImageView(avatar_img, style=Pack(height=48, margin_right=10))
                header.add(avatar_view)
            except Exception:
                header.add(toga.Box(style=Pack(width=48, height=48, margin_right=10)))
        else:
            header.add(toga.Box(style=Pack(width=48, height=48, margin_right=10)))

        header.add(
            toga.Button(
                f"@{author}",
                on_press=lambda w, a=author: self._view_profile(a),
                style=Pack(margin_right=10),
            )
        )
        header.add(toga.Label(date_str, style=Pack(flex=1)))
        inner.add(header)

        # Repost indicator
        if post.get("repost", False):
            inner.add(toga.Label(f"Reposted from @{post.get('repost_author', '')}", style=Pack(margin_bottom=5)))

        # Full post content (split by newlines for clean returns)
        if content:
            content_box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=10, padding=8))
            for paragraph in content.split("\n"):
                if paragraph.strip():
                    content_box.add(toga.Label(paragraph.strip(), style=Pack(margin_bottom=3)))
            inner.add(content_box)

        # Post image
        if post.get("image"):
            inner.add(
                toga.Button(
                    "[View Image]",
                    on_press=lambda w, p=post: self._on_tap_post_image(p),
                    style=Pack(margin_bottom=10),
                )
            )

        # Actions
        actions = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        like_count = post.get("like_count", 0)
        actions.add(toga.Button(
            f"Like ({like_count})",
            on_press=lambda w, pid=post_id: self._handle_like(pid),
            style=Pack(margin_right=5),
        ))
        actions.add(toga.Button(
            "Repost",
            on_press=lambda w, pid=post_id: self._handle_repost(pid),
            style=Pack(margin_right=5),
        ))
        if author == app_state.get("username"):
            actions.add(toga.Button(
                "Delete",
                on_press=lambda w, pid=post_id: self._handle_delete_post(pid),
            ))
        inner.add(actions)

        # Comments
        inner.add(toga.Label(f"Comments ({len(comments)})", style=Pack(margin_top=10, margin_bottom=8)))

        if comments:
            for comment in comments:
                c_author = comment.get("author", "[deleted]")
                c_text = comment.get("content", "")
                c_box = toga.Box(style=Pack(direction=COLUMN, padding=6, margin_bottom=6, margin_left=8))
                # Comment header with optional small avatar
                c_header = toga.Box(style=Pack(direction=ROW, margin_bottom=2))
                c_av_data = self._avatar_cache.get(c_author)
                if c_av_data:
                    try:
                        c_av_img = toga.Image(data=c_av_data)
                        c_av_view = toga.ImageView(c_av_img, style=Pack(height=20, margin_right=5))
                        c_header.add(c_av_view)
                    except Exception:
                        pass
                c_header.add(toga.Label(f"@{c_author}", style=Pack(margin_right=5)))
                c_box.add(c_header)
                # Comment text split by newlines for clean returns
                for line in c_text.split("\n"):
                    if line.strip():
                        c_box.add(toga.Label(line.strip(), style=Pack(margin_bottom=2)))
                inner.add(c_box)
        else:
            inner.add(toga.Label("No comments yet.", style=Pack(margin_bottom=5)))

        # Comment input at bottom (inside scroll so keyboard pushes it up)
        comment_row = toga.Box(style=Pack(direction=ROW, margin_top=8, padding_bottom=20))
        self.detail_comment_input = toga.TextInput(
            placeholder="Write a comment...", style=Pack(flex=1, margin_right=5)
        )
        comment_row.add(self.detail_comment_input)
        comment_row.add(
            toga.Button("OK", on_press=lambda w, pid=post_id: self._handle_add_comment(pid))
        )
        inner.add(comment_row)

        scroll = toga.ScrollContainer(style=Pack(flex=1))
        scroll.content = inner
        self.root_box.add(scroll)

    # ========================================================================
    # VIEW OTHER USER PROFILE
    # ========================================================================
    def _view_profile(self, username: str):
        if username == app_state.get("username"):
            self._switch_tab("profile")
            return
        app_state["viewing_profile"] = username
        for child in list(self.content_area.children):
            self.content_area.remove(child)
        self._load_profile_tab(username)

    # ========================================================================
    # SEARCH TAB
    # ========================================================================
    def _load_search_tab(self):
        search_row = toga.Box(style=Pack(direction=ROW, margin_bottom=8))
        self.search_input = toga.TextInput(
            placeholder="Search users or posts...", style=Pack(flex=1, margin_right=5)
        )
        search_row.add(self.search_input)
        search_row.add(toga.Button("Search", on_press=self._handle_search))
        self.content_area.add(search_row)

        tag_row = toga.Box(style=Pack(direction=ROW, margin_bottom=12))
        self.tag_input = toga.TextInput(
            placeholder="Search by hashtag...", style=Pack(flex=1, margin_right=5)
        )
        tag_row.add(self.tag_input)
        tag_row.add(toga.Button("Search Tag", on_press=self._handle_tag_search))
        self.content_area.add(tag_row)

        self.search_results = toga.Box(style=Pack(direction=COLUMN))
        self.content_area.add(self.search_results)

    def _handle_search(self, widget):
        query = self.search_input.value.strip()
        if not query:
            return
        self._clear_children(self.search_results)
        self.search_results.add(toga.Label("Searching...", style=Pack(margin_bottom=5)))
        self._run_in_thread(self._do_search, query, "")

    def _handle_tag_search(self, widget):
        tag = self.tag_input.value.strip().lstrip("#")
        if not tag:
            return
        self._clear_children(self.search_results)
        self.search_results.add(toga.Label("Searching...", style=Pack(margin_bottom=5)))
        self._run_in_thread(self._do_search, "", tag)

    def _do_search(self, query: str, tag: str):
        try:
            posts = api.get_posts()
            posts.sort(key=lambda p: int(p.get("created_at", 0)), reverse=True)
            if tag:
                filtered = [p for p in posts if tag in p.get("tags", [])]
                label = f"Results for #{tag}"
            else:
                q_lower = query.lower()
                filtered = [
                    p for p in posts
                    if q_lower in p.get("content", "").lower()
                    or q_lower in p.get("author", "").lower()
                ]
                label = f'Results for "{query}"'
            # Render immediately (text only), avatars load after
            self._on_main_thread(self._render_search_results, filtered, label)
        except Exception as e:
            self._on_main_thread(self._render_search_results, [], f"Error: {e}")

    def _render_search_results(self, posts, label):
        self._clear_children(self.search_results)
        self.search_results.add(toga.Label(label, style=Pack(margin_bottom=8)))

        if not posts:
            self.search_results.add(toga.Label("No results found.", style=Pack(margin_bottom=5)))
            return

        for post in posts[:15]:
            self.search_results.add(self._build_post_card(post))

    # ========================================================================
    # PROFILE TAB
    # ========================================================================
    def _load_profile_tab(self, username: str):
        is_self = username == app_state.get("username")

        header = toga.Box(style=Pack(direction=COLUMN, padding=10, margin_bottom=10))

        # Avatar placeholder
        self._profile_avatar_box = toga.Box(style=Pack(direction=COLUMN, alignment=CENTER, margin_bottom=8))
        self._profile_avatar_box.add(toga.Box(style=Pack(width=64, height=64)))
        header.add(self._profile_avatar_box)

        header.add(toga.Label(f"@{username}", style=Pack(margin_bottom=3, alignment=CENTER)))

        self.profile_bio_label = toga.Label("Loading profile...", style=Pack(margin_bottom=5, alignment=CENTER))
        header.add(self.profile_bio_label)

        stats = toga.Box(style=Pack(direction=ROW, margin_bottom=5))
        self.profile_posts_count = toga.Label("Posts: ...", style=Pack(margin_right=15))
        self.profile_followers = toga.Label("Followers: ...", style=Pack(margin_right=15))
        self.profile_following = toga.Label("Following: ...")
        stats.add(self.profile_posts_count, self.profile_followers, self.profile_following)
        header.add(stats)

        if not is_self:
            btn_row = toga.Box(style=Pack(direction=ROW, margin_bottom=8))
            self.follow_btn = toga.Button(
                "Follow",
                on_press=lambda w, u=username: self._handle_follow(u),
                style=Pack(margin_right=5),
            )
            btn_row.add(self.follow_btn)
            btn_row.add(
                toga.Button(
                    "Message",
                    on_press=lambda w, u=username: self._start_chat_with(u),
                    style=Pack(margin_right=5),
                )
            )
            btn_row.add(
                toga.Button(
                    "Block",
                    on_press=lambda w, u=username: self._handle_block(u),
                )
            )
            header.add(btn_row)
            header.add(
                toga.Button("Back to My Profile", on_press=lambda w: self._switch_tab("profile"), style=Pack(margin_top=5))
            )
        else:
            header.add(toga.Button("Settings", on_press=self._show_settings, style=Pack(margin_top=5)))

        self.content_area.add(header)
        self.content_area.add(toga.Label("Posts", style=Pack(margin_bottom=8)))

        self.profile_posts_area = toga.Box(style=Pack(direction=COLUMN))
        self.profile_posts_area.add(toga.Label("Loading...", style=Pack(margin_bottom=5)))
        self.content_area.add(self.profile_posts_area)

        self._run_in_thread(self._fetch_profile, username)

    def _fetch_profile(self, username: str):
        try:
            profile_info = api.get_profile(username)
            avatar_data = api.fetch_avatar(username)
            if avatar_data:
                self._avatar_cache[username] = avatar_data

            posts = api.get_posts()
            user_posts = [p for p in posts if p.get("author") == username and p.get("status") != "deleted"]
            user_posts.sort(key=lambda p: int(p.get("created_at", 0)), reverse=True)

            self._on_main_thread(
                self._render_profile, user_posts, username, profile_info, avatar_data
            )
        except Exception as e:
            self._on_main_thread(self._set_label_text, self.profile_bio_label, f"Error: {e}")

    def _render_profile(self, posts, username, profile_info, avatar_data):
        is_self = username == app_state.get("username")

        self._clear_children(self._profile_avatar_box)
        if avatar_data:
            try:
                avatar_img = toga.Image(data=avatar_data)
                avatar_view = toga.ImageView(avatar_img, style=Pack(height=64))
                self._profile_avatar_box.add(avatar_view)
            except Exception:
                self._profile_avatar_box.add(toga.Label("(no avatar)"))
        else:
            self._profile_avatar_box.add(toga.Label("(no avatar)"))

        if profile_info:
            display = profile_info.get("display_name", username)
            bio = profile_info.get("bio", "")
            followers = profile_info.get("followers", 0)
            following = profile_info.get("following", 0)
            is_following = profile_info.get("is_following", False)

            info_text = display
            if bio:
                info_text = f"{info_text}\n{bio}"
            self._set_label_text(self.profile_bio_label, info_text)
            self._set_label_text(self.profile_followers, f"Followers: {followers}")
            self._set_label_text(self.profile_following, f"Following: {following}")

            if not is_self and hasattr(self, "follow_btn"):
                if is_following:
                    self.follow_btn.text = "Unfollow"
                    self.follow_btn.on_press = lambda w, u=username: self._handle_unfollow(u)
                else:
                    self.follow_btn.text = "Follow"
                    self.follow_btn.on_press = lambda w, u=username: self._handle_follow(u)
        else:
            self._set_label_text(self.profile_bio_label, f"@{username}'s profile")

        self._set_label_text(self.profile_posts_count, f"Posts: {len(posts)}")

        self._clear_children(self.profile_posts_area)
        if not posts:
            self.profile_posts_area.add(toga.Label("No posts yet.", style=Pack(margin_bottom=5)))
            return
        for post in posts[:15]:
            self.profile_posts_area.add(self._build_post_card(post, avatar_data=avatar_data))

    def _handle_follow(self, username: str):
        def do_follow():
            try:
                api.follow(username)
                self._on_main_thread(self._view_profile, username)
            except Exception:
                pass
        self._run_in_thread(do_follow)

    def _handle_unfollow(self, username: str):
        def do_unfollow():
            try:
                api.unfollow(username)
                self._on_main_thread(self._view_profile, username)
            except Exception:
                pass
        self._run_in_thread(do_unfollow)

    def _handle_block(self, username: str):
        def do_block():
            try:
                api.block(username)
                self._on_main_thread(self._switch_tab, "feed")
            except Exception:
                pass
        self._run_in_thread(do_block)

    # ========================================================================
    # SETTINGS
    # ========================================================================
    def _show_settings(self, widget=None):
        self._clear()

        box = toga.Box(style=Pack(direction=COLUMN, padding=20, alignment=CENTER, flex=1))

        box.add(toga.Label("Settings", style=Pack(margin_bottom=15, alignment=CENTER)))
        box.add(toga.Button("Back", on_press=self.show_main_app, style=Pack(margin_bottom=15)))

        box.add(toga.Label("Server URL:", style=Pack(margin_bottom=5)))
        self.settings_server = toga.TextInput(style=Pack(margin_bottom=10))
        self.settings_server.value = BASE_URL
        box.add(self.settings_server)

        box.add(toga.Button("Save & Return", on_press=self._save_settings, style=Pack(margin_bottom=15)))

        box.add(toga.Label("Followed Tags", style=Pack(margin_bottom=8, alignment=CENTER)))
        tag_row = toga.Box(style=Pack(direction=ROW, margin_bottom=8))
        self.new_tag_input = toga.TextInput(placeholder="Add hashtag...", style=Pack(flex=1, margin_right=5))
        tag_row.add(self.new_tag_input)
        tag_row.add(toga.Button("Follow Tag", on_press=self._handle_follow_tag))
        box.add(tag_row)

        scroll = toga.ScrollContainer(style=Pack(flex=1))
        scroll.content = box
        self.root_box.add(scroll)

    def _save_settings(self, widget):
        global BASE_URL, api
        new_url = self.settings_server.value.strip().rstrip("/")
        if new_url:
            BASE_URL = new_url
            api = SeeyahAPI(BASE_URL)
        self.show_main_app()

    def _handle_follow_tag(self, widget):
        tag = self.new_tag_input.value.strip().lstrip("#")
        if tag:
            self._run_in_thread(api.follow_tag, tag)
            self.new_tag_input.value = ""

    # ========================================================================
    # MESSAGES TAB - Server-loaded
    # ========================================================================
    def _load_messages_tab(self):
        self.content_area.add(toga.Label("Direct Messages", style=Pack(margin_bottom=10)))

        msg_row = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        self.msg_to_input = toga.TextInput(
            placeholder="Send to @username...", style=Pack(flex=1, margin_right=5)
        )
        msg_row.add(self.msg_to_input)
        msg_row.add(toga.Button("Chat", on_press=self._open_conversation))
        self.content_area.add(msg_row)

        self.content_area.add(toga.Label("Conversations", style=Pack(margin_bottom=5)))

        self.conversations_area = toga.Box(style=Pack(direction=COLUMN))
        self.conversations_area.add(toga.Label("Loading conversations...", style=Pack(margin_bottom=5)))
        self.content_area.add(self.conversations_area)

        self._run_in_thread(self._fetch_conversations)

    def _fetch_conversations(self):
        try:
            convs = api.get_conversations()
            self._on_main_thread(self._render_conversations, convs)
        except Exception as e:
            self._on_main_thread(
                self._set_label_text,
                self.conversations_area.children[0] if self.conversations_area.children else None,
                f"Error: {e}",
            )

    def _render_conversations(self, convs):
        self._clear_children(self.conversations_area)

        if not convs:
            self.conversations_area.add(
                toga.Label("No conversations yet. Start one above!", style=Pack(margin_bottom=5))
            )
            return

        for conv in convs:
            row = toga.Box(style=Pack(direction=COLUMN, padding=8, margin_bottom=4))
            with_user = conv.get("with", "")
            preview = conv.get("last_message", "")

            header = toga.Box(style=Pack(direction=ROW))
            header.add(
                toga.Button(
                    f"@{with_user}",
                    on_press=lambda w, u=with_user: self._open_existing_chat(u),
                    style=Pack(margin_right=10),
                )
            )
            row.add(header)
            if preview:
                row.add(toga.Label(preview, style=Pack(margin_left=10)))
            self.conversations_area.add(row)

    def _open_conversation(self, widget):
        to_user = self.msg_to_input.value.strip().lstrip("@")
        if not to_user:
            return
        self._start_chat_with(to_user)

    def _open_existing_chat(self, username: str):
        self._start_chat_with(username)

    def _start_chat_with(self, username: str):
        self._clear()

        # Everything inside one scroll container so the input moves with the keyboard
        inner = toga.Box(style=Pack(direction=COLUMN, padding=10))

        header = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        header.add(toga.Button("Back", on_press=self.show_main_app, style=Pack(margin_right=10)))
        header.add(toga.Label(f"Chat with @{username}"))
        inner.add(header)

        self.chat_messages_area = toga.Box(style=Pack(direction=COLUMN, padding=5))
        self.chat_messages_area.add(toga.Label("Loading conversation...", style=Pack(margin_bottom=5)))
        inner.add(self.chat_messages_area)

        # Input at the bottom, INSIDE the scroll so iOS keyboard pushes it up
        input_row = toga.Box(style=Pack(direction=ROW, margin_top=8, padding_bottom=20))
        self.chat_input = toga.TextInput(
            placeholder="Type a message...", style=Pack(flex=1, margin_right=5)
        )
        input_row.add(self.chat_input)
        input_row.add(toga.Button("Send", on_press=lambda w: self._send_chat_message(username)))
        inner.add(input_row)

        chat_scroll = toga.ScrollContainer(style=Pack(flex=1))
        chat_scroll.content = inner
        self.root_box.add(chat_scroll)
        self._run_in_thread(self._init_and_load_chat, username)

    def _init_and_load_chat(self, username: str):
        try:
            conv_id = api.start_conversation(username)
            if conv_id:
                result = api.get_messages(conv_id)
                self._on_main_thread(self._render_loaded_messages, result, username)
            else:
                self._on_main_thread(self._set_label_text,
                    self.chat_messages_area.children[0] if self.chat_messages_area.children else None,
                    f"Start chatting with @{username}!")
        except Exception:
            self._on_main_thread(self._set_label_text,
                self.chat_messages_area.children[0] if self.chat_messages_area.children else None,
                f"Start chatting with @{username}!")

    def _render_loaded_messages(self, result, with_user: str):
        self._clear_children(self.chat_messages_area)

        messages = result.get("messages", [])
        current_user = app_state.get("username", "")

        if not messages:
            self.chat_messages_area.add(
                toga.Label(f"No messages yet with @{with_user}. Say hi!", style=Pack(margin_bottom=5))
            )
            return

        for msg in messages:
            is_sent = msg.get("from") == current_user
            text = msg.get("message", "")
            timestamp = msg.get("created_at", 0)

            try:
                dt = datetime.fromtimestamp(int(timestamp))
                time_str = dt.strftime("%H:%M")
            except (ValueError, TypeError, OSError):
                time_str = ""

            bubble = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin_bottom=6,
                    padding=8,
                    margin_left=40 if is_sent else 5,
                    margin_right=5 if is_sent else 40,
                )
            )

            sender = "You" if is_sent else f"@{msg.get('from', '?')}"
            bubble.add(toga.Label(f"{sender}: {text}"))
            if time_str:
                bubble.add(toga.Label(time_str))

            self.chat_messages_area.add(bubble)

    def _send_chat_message(self, to_user: str):
        message = self.chat_input.value.strip()
        if not message:
            return
        self.chat_input.value = ""

        bubble = toga.Box(
            style=Pack(direction=COLUMN, margin_bottom=6, padding=8, margin_left=40, margin_right=5)
        )
        bubble.add(toga.Label(f"You: {message}"))
        try:
            bubble.add(toga.Label(datetime.now().strftime("%H:%M")))
        except Exception:
            pass
        self.chat_messages_area.add(bubble)

        def do_send():
            try:
                result = api.send_message(to_user, message)
                if not result.get("success"):
                    self._on_main_thread(self._add_chat_label, f"Failed to send to @{to_user}.")
            except Exception as e:
                self._on_main_thread(self._add_chat_label, f"[Error: {e}]")

        self._run_in_thread(do_send)

    def _add_chat_label(self, text: str):
        self.chat_messages_area.add(toga.Label(text, style=Pack(margin_bottom=4)))

    # ========================================================================
    # NOTIFICATIONS TAB
    # ========================================================================
    def _load_notifications_tab(self):
        self.notif_loading = toga.Label("Loading notifications...", style=Pack(margin_bottom=10))
        self.content_area.add(self.notif_loading)
        self._run_in_thread(self._fetch_notifications)

    def _fetch_notifications(self):
        try:
            result = api.get_notifications()
            self._on_main_thread(self._render_notifications, result)
        except Exception as e:
            self._on_main_thread(self._render_notifications, {"count": 0, "notifications": [], "error": str(e)})

    def _render_notifications(self, result):
        if self.notif_loading in self.content_area.children:
            self.content_area.remove(self.notif_loading)

        count = result.get("count", 0)
        notifs = result.get("notifications", [])

        # Store notifications data for tap handling
        self._notifications_data = notifs

        # Header with always-visible "Mark all read"
        header = toga.Box(style=Pack(direction=ROW, margin_bottom=10, alignment=CENTER))
        header.add(toga.Label(f"Notifications ({count} unread)", style=Pack(flex=1)))
        header.add(
            toga.Button("Mark all read", on_press=self._handle_mark_read, style=Pack(margin_left=10))
        )
        self.content_area.add(header)

        if not notifs:
            self.content_area.add(
                toga.Label("No notifications yet!", style=Pack(margin_top=20, alignment=CENTER))
            )
            return

        for idx, notif in enumerate(notifs):
            notif_type = notif.get("type", "")
            from_user = notif.get("from", "")
            message = notif.get("message", "")
            created_at = notif.get("created_at", 0)
            notif_link = notif.get("link", "")

            try:
                dt = datetime.fromtimestamp(int(created_at))
                time_str = dt.strftime("%d %b %Y, %H:%M")
            except (ValueError, TypeError, OSError):
                time_str = "Unknown"

            icon = NOTIF_ICONS.get(notif_type, notif_type.upper())

            card = toga.Box(style=Pack(direction=COLUMN, padding=10, margin_bottom=6))
            card.add(toga.Label(f"[{icon}] {notif_type.upper()}", style=Pack(margin_bottom=2)))
            card.add(toga.Label(f"@{from_user} {message}", style=Pack(margin_bottom=2)))
            card.add(toga.Label(time_str))

            # Clickable button if the notification has a link
            if notif_link:
                card.add(
                    toga.Button(
                        "View",
                        on_press=lambda w, i=idx: self._handle_notif_tap(i),
                        style=Pack(margin_top=4),
                    )
                )

            self.content_area.add(card)

    def _handle_mark_read(self, widget):
        def do_mark():
            api.mark_notifications_read()
            self._on_main_thread(self._load_notifications_tab)
        self._run_in_thread(do_mark)

    def _handle_notif_tap(self, notif_index: int):
        """Handle tapping a notification - navigate to the linked content."""
        notifs = getattr(self, '_notifications_data', [])
        if notif_index >= len(notifs):
            return
        notif = notifs[notif_index]
        link = notif.get("link", "")
        if not link:
            return

        # Check if it links to a post
        post_match = re.search(r'post\.php\?id=([^&]+)', link)
        if post_match:
            post_id = post_match.group(1)
            # Try cached posts first
            if hasattr(self, '_all_posts') and self._all_posts:
                for p in self._all_posts:
                    if p.get("id") == post_id:
                        self._show_post_detail(p)
                        return
            # Not cached - fetch from server
            self._run_in_thread(self._fetch_and_show_post, post_id)
            return

        # Check if it links to a profile
        profile_match = re.search(r'profile\.php\?user=([^&]+)', link)
        if profile_match:
            username = profile_match.group(1)
            self._view_profile(username)
            return

    def _fetch_and_show_post(self, post_id: str):
        """Fetch all posts and show the one matching post_id."""
        try:
            posts = api.get_posts()
            for p in posts:
                if p.get("id") == post_id:
                    self._on_main_thread(self._show_post_detail, p)
                    return
        except Exception:
            pass

    # ========================================================================
    # Action Handlers
    # ========================================================================
    def _handle_login(self, widget):
        username = self.login_username.value.strip()
        password = self.login_password.value.strip()
        if not username or not password:
            self._set_label_text(self.login_error, "Please fill in all fields.")
            return

        self._update_base_url()

        def do_login():
            try:
                r = api.login(username, password)
                text = r.text.lower()
                if "2fa" in text or "verification" in text:
                    self._on_main_thread(self._show_2fa_form)
                else:
                    app_state["username"] = username
                    self._on_main_thread(self.show_main_app)
            except Exception as e:
                self._on_main_thread(self._set_label_text, self.login_error, f"Error: {e}")

        self._run_in_thread(do_login)

    def _handle_2fa(self, widget):
        code = self.twofa_code.value.strip()
        if not code:
            return

        def do_verify():
            try:
                r = api.verify_2fa(code)
                if r.status_code == 200:
                    app_state["username"] = self.login_username.value.strip()
                    self._on_main_thread(self.show_main_app)
                else:
                    self._on_main_thread(self._set_label_text, self.login_error, "Invalid 2FA code.")
            except Exception as e:
                self._on_main_thread(self._set_label_text, self.login_error, f"Error: {e}")

        self._run_in_thread(do_verify)

    def _handle_register(self, widget):
        username = self.reg_username.value.strip()
        password = self.reg_password.value.strip()
        if not username or not password:
            self._set_label_text(self.reg_error, "Username and password required.")
            return

        self._update_base_url()

        def do_register():
            try:
                display = self.reg_display.value.strip()
                r = api.register(username, password, display)
                if r.status_code == 200:
                    app_state["username"] = username
                    self._on_main_thread(self.show_main_app)
                else:
                    self._on_main_thread(self._set_label_text, self.reg_error, "Registration failed.")
            except Exception as e:
                self._on_main_thread(self._set_label_text, self.reg_error, f"Error: {e}")

        self._run_in_thread(do_register)

    def _handle_logout(self, widget):
        def do_logout():
            try:
                api.logout()
            except Exception:
                pass
            self._on_main_thread(self.show_login_screen)
        self._run_in_thread(do_logout)

    def _handle_create_post(self, widget):
        content = self.composer_input.value.strip()
        if not content:
            return
        self.composer_input.value = ""

        def do_post():
            try:
                api.create_post(content)
                self._on_main_thread(self._refresh_feed)
            except Exception:
                pass

        self._run_in_thread(do_post)

    def _handle_like(self, post_id: str):
        self._run_in_thread(lambda: api.toggle_like(post_id))

    def _handle_repost(self, post_id: str):
        self._run_in_thread(lambda: api.repost(post_id))

    def _handle_delete_post(self, post_id: str):
        def do_delete():
            try:
                api.delete_post(post_id, "soft")
                self._on_main_thread(self._refresh_feed)
            except Exception:
                pass
        self._run_in_thread(do_delete)

    def _handle_add_comment(self, post_id: str):
        content = self.detail_comment_input.value.strip()
        if not content or not post_id:
            return
        self.detail_comment_input.value = ""

        def do_comment():
            try:
                api.add_comment(post_id, content)
                self._on_main_thread(self.show_main_app)
            except Exception:
                pass

        self._run_in_thread(do_comment)

    # ========================================================================
    # Utilities
    # ========================================================================
    def _set_label_text(self, label_widget, new_text: str):
        try:
            if label_widget is not None:
                label_widget.text = new_text
        except Exception:
            pass

    def _clear_children(self, box: toga.Box):
        for child in list(box.children):
            box.remove(child)

    def _update_base_url(self):
        global BASE_URL, api
        try:
            new_url = self.server_url_input.value.strip().rstrip("/")
            if new_url and new_url != BASE_URL:
                BASE_URL = new_url
                api = SeeyahAPI(BASE_URL)
        except Exception:
            pass


# ===========================================================================
# Entry Point
# ===========================================================================
def main():
    return SeeyahApp(
        formal_name="Seeyah",
        app_id="com.seeyah.app",
    )


if __name__ == "__main__":
    main().main_loop()