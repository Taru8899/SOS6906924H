#!/usr/bin/env python3
"""
SOS69069 24H Miner
- Real EIP-712 signing
- Unique news title per signature
- Bigger fonts, clickable green tx links, Trust/Push/Effective
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.scrollview import ScrollView
from kivy.uix.image import Image
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform
from kivy.storage.jsonstore import JsonStore
from kivy.metrics import dp
import threading
import time
import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import webbrowser

from pure_crypto import keccak256, sign as ecdsa_sign, privkey_to_pubkey, pubkey_to_address
import requests
import tx as txmod
import rpc as rpcmod

CONTRACT = "0x7373DBC24Dcd785896E8Ac3d5372c6ced9B75a8A"
DEFAULT_INTENDED = "0x1C10e6574ee696f54b21A611a21313E4714628ad"
DEFAULT_RPC = "https://ethereum-rpc.publicnode.com"
DEFAULT_GAS_MAX = "1.5"
STORE = "sos24h_task.json"
CHAIN_ID = 1

EIP712_DOMAIN_TYPEHASH = keccak256(
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
RECORD_TYPEHASH = keccak256(
    b"Record(address signer,address intendedTo,bytes32 payloadHash,bytes32 metadataHash)"
)


def _pad32(b: bytes) -> bytes:
    return b.rjust(32, b"\x00") if len(b) < 32 else b[:32]


def _addr_bytes(addr: str) -> bytes:
    return bytes.fromhex(addr[2:].lower().zfill(40))


def domain_separator() -> bytes:
    return keccak256(
        EIP712_DOMAIN_TYPEHASH
        + keccak256(b"69069")
        + keccak256(b"1")
        + CHAIN_ID.to_bytes(32, "big")
        + _pad32(_addr_bytes(CONTRACT))
    )


def record_struct_hash(signer, intended_to, payload_hash, metadata):
    return keccak256(
        RECORD_TYPEHASH
        + _pad32(_addr_bytes(signer))
        + _pad32(_addr_bytes(intended_to))
        + payload_hash
        + keccak256(metadata.encode("utf-8"))
    )


def eip712_digest(signer, intended_to, payload_hash, metadata):
    return keccak256(b"\x19\x01" + domain_separator() + record_struct_hash(signer, intended_to, payload_hash, metadata))


def sign_record(priv_int, signer, intended_to, payload_hash, metadata):
    digest = eip712_digest(signer, intended_to, payload_hash, metadata)
    r, s, v = ecdsa_sign(priv_int, digest)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])


def fetch_news_titles(max_titles=40):
    feeds = [
        "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
        "https://feeds.reuters.com/reuters/topNews",
    ]
    titles, seen = [], set()
    for url in feeds:
        if len(titles) >= max_titles:
            break
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "SOS69069/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                if len(titles) >= max_titles:
                    break
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    title = re.sub(r"\s+", " ", title_el.text).strip()
                    title = re.split(r"\s+-\s+", title)[0].strip()[:64]
                    key = title.lower()
                    if len(title) > 12 and key not in seen:
                        seen.add(key)
                        titles.append(title)
        except Exception:
            continue
    return titles


class NewsPool:
    def __init__(self):
        self.titles = []
        self.index = 0
        self.lock = threading.Lock()

    def refresh(self):
        new = fetch_news_titles(50)
        with self.lock:
            if new:
                self.titles = new
                self.index = 0

    def next(self):
        with self.lock:
            if not self.titles:
                return f"sos24h-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"[:64]
            title = self.titles[self.index % len(self.titles)]
            self.index += 1
            if self.index >= len(self.titles) - 2:
                threading.Thread(target=self.refresh, daemon=True).start()
            return title


def open_url(url):
    try:
        if platform == "android":
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            PythonActivity.mActivity.startActivity(intent)
        else:
            webbrowser.open(url)
    except Exception:
        try:
            webbrowser.open(url)
        except Exception:
            pass


class PasswordPopup(Popup):
    def __init__(self, on_success, mode="unlock", **kwargs):
        super().__init__(title="Password", size_hint=(0.9, 0.45), **kwargs)
        self.on_success = on_success
        layout = BoxLayout(orientation="vertical", padding=16, spacing=12)
        self.pwd = TextInput(hint_text="Password", password=True, multiline=False, font_size=dp(22), size_hint_y=None, height=dp(56))
        layout.add_widget(self.pwd)
        if mode == "set":
            self.pwd2 = TextInput(hint_text="Confirm password", password=True, multiline=False, font_size=dp(22), size_hint_y=None, height=dp(56))
            layout.add_widget(self.pwd2)
            btn = Button(text="SAVE & PROTECT", background_color=(0.1, 0.7, 0.3, 1), font_size=dp(22), bold=True, size_hint_y=None, height=dp(56))
        else:
            self.pwd2 = None
            btn = Button(text="UNLOCK", background_color=(0.1, 0.7, 0.3, 1), font_size=dp(22), bold=True, size_hint_y=None, height=dp(56))
        btn.bind(on_press=lambda x: self._ok(mode))
        layout.add_widget(btn)
        self.content = layout

    def _ok(self, mode):
        p1 = self.pwd.text.strip()
        if mode == "set" and (not p1 or p1 != (self.pwd2.text.strip() if self.pwd2 else "")):
            return
        self.dismiss()
        self.on_success(p1)


class LogLabel(Label):
    """Markup label that opens ethereum tx links on click."""
    def on_ref_press(self, ref):
        if ref.startswith("http"):
            open_url(ref)


class MinerUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), **kwargs)
        Window.clearcolor = (0.05, 0.05, 0.08, 1)
        self.mining = False
        self.thread = None
        self.password = None
        self.store = JsonStore(STORE)
        self.total_spent = 0.0
        self.total_sigs = 0
        self.push_val = "-"
        self.trust_val = "-"
        self.eff_val = "-"
        self.news_pool = NewsPool()
        self.signer_addr = None

        # Top bar
        top = BoxLayout(size_hint_y=None, height=dp(84), spacing=dp(10), padding=[dp(4), dp(4), dp(4), dp(4)])
        try:
            top.add_widget(Image(source="icon.png", size_hint=(None, None), size=(dp(76), dp(76))))
        except Exception:
            top.add_widget(Label(text="SOS", size_hint=(None, None), size=(dp(76), dp(76)), font_size=dp(28), bold=True))
        top.add_widget(Label(text="SOS69069 24H", font_size=dp(32), bold=True, halign="left", valign="middle"))
        self.add_widget(top)

        # Contract
        self.add_widget(Label(
            text=f"Contract: {CONTRACT}",
            size_hint_y=None, height=dp(34), font_size=dp(16), bold=True,
            color=(0.45, 0.95, 0.55, 1), halign="left"
        ))

        # Fields
        self.add_widget(Label(text="Private Key", size_hint_y=None, height=dp(30), font_size=dp(20), bold=True, halign="left"))
        self.pk = TextInput(hint_text="0x...", password=True, multiline=False, font_size=dp(20), size_hint_y=None, height=dp(56))
        self.add_widget(self.pk)

        self.add_widget(Label(text="IntendedTo Address", size_hint_y=None, height=dp(30), font_size=dp(20), bold=True, halign="left"))
        self.target = TextInput(text=DEFAULT_INTENDED, multiline=False, font_size=dp(18), size_hint_y=None, height=dp(56))
        self.add_widget(self.target)

        self.add_widget(Label(text="RPC URL", size_hint_y=None, height=dp(30), font_size=dp(20), bold=True, halign="left"))
        self.rpc = TextInput(text=DEFAULT_RPC, multiline=False, font_size=dp(16), size_hint_y=None, height=dp(56))
        self.add_widget(self.rpc)

        gas_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        self.gas = TextInput(text=DEFAULT_GAS_MAX, hint_text="Gas max gwei", font_size=dp(20), size_hint_x=0.4)
        gas_row.add_widget(self.gas)
        self.save_gas = CheckBox(size_hint_x=None, width=dp(36))
        gas_row.add_widget(self.save_gas)
        gas_row.add_widget(Label(text="Save gas for task", font_size=dp(18), bold=True, size_hint_x=0.5, halign="left"))
        self.add_widget(gas_row)

        # Buttons
        btn_row = BoxLayout(size_hint_y=None, height=dp(64), spacing=dp(10))
        self.start_btn = Button(text="START / CONTINUE", background_color=(0.05, 0.75, 0.25, 1), font_size=dp(22), bold=True)
        self.start_btn.bind(on_press=self.on_start)
        self.stop_btn = Button(text="STOP", background_color=(0.8, 0.15, 0.15, 1), font_size=dp(22), bold=True, disabled=True)
        self.stop_btn.bind(on_press=self.on_stop)
        btn_row.add_widget(self.start_btn)
        btn_row.add_widget(self.stop_btn)
        self.add_widget(btn_row)

        # Stats
        self.stats = Label(
            text="Push: - | Trust: - | Effective: -\nSpent: 0.00000 ETH | Sigs: 0",
            size_hint_y=None, height=dp(70), font_size=dp(20), bold=True,
            halign="left", valign="middle"
        )
        self.stats.bind(size=self.stats.setter("text_size"))
        self.add_widget(self.stats)

        self.status_line = Label(
            text="News pool: loading...", size_hint_y=None, height=dp(34),
            font_size=dp(18), bold=True, color=(0.7, 0.85, 1, 1)
        )
        self.add_widget(self.status_line)

        # Large scrollable log with markup for green clickable links
        self.log_label = LogLabel(
            text="Ready. Enter key and press START.\n",
            size_hint_y=None, font_size=dp(18),
            halign="left", valign="top",
            markup=True, color=(0.9, 0.9, 0.9, 1)
        )
        self.log_label.bind(texture_size=self._update_log_height)
        self.log_label.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0], None)))
        sc = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        sc.add_widget(self.log_label)
        self.add_widget(sc)

        Clock.schedule_once(self.try_load, 0.4)
        Clock.schedule_once(self._load_news, 0.8)

        if platform == "android":
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.WAKE_LOCK])
            except Exception:
                pass

    def _update_log_height(self, instance, size):
        instance.height = max(size[1], dp(400))

    def log(self, msg, tx_url=None):
        """Add a log entry. If tx_url given, put green clickable link on next line."""
        ts = datetime.now().strftime("%H:%M:%S")
        # Escape markup special chars in msg
        safe = (msg.replace("&", "&amp;").replace("[", "(").replace("]", ")"))
        line = f"[{ts}] {safe}"
        if tx_url:
            line += f"\n[color=33ff66][ref={tx_url}]{tx_url}[/ref][/color]"
        self.log_label.text = line + "\n" + self.log_label.text[:3500]

    def _load_news(self, dt):
        def work():
            self.news_pool.refresh()
            n = len(self.news_pool.titles)
            Clock.schedule_once(lambda d: setattr(self.status_line, "text", f"News pool: {n} titles ready"), 0)
        threading.Thread(target=work, daemon=True).start()

    def try_load(self, dt):
        if self.store.exists("task"):
            self.log("Saved task found – enter password")
            PasswordPopup(on_success=self.unlock, mode="unlock").open()

    def unlock(self, pwd):
        try:
            d = self.store.get("task")
            if d.get("pwd_hash") == hashlib.sha256(pwd.encode()).hexdigest():
                self.password = pwd
                self.pk.text = d.get("pk", "")
                self.target.text = d.get("intended", DEFAULT_INTENDED)
                self.rpc.text = d.get("rpc", DEFAULT_RPC)
                self.gas.text = d.get("gas_max", DEFAULT_GAS_MAX)
                self.total_spent = d.get("spent", 0.0)
                self.total_sigs = d.get("sigs", 0)
                self.log("Task unlocked")
            else:
                self.log("Wrong password")
        except Exception as e:
            self.log(f"Load error: {e}")

    def save(self, pwd):
        self.store.put("task",
            pwd_hash=hashlib.sha256(pwd.encode()).hexdigest(),
            pk=self.pk.text.strip(),
            intended=self.target.text.strip(),
            rpc=self.rpc.text.strip(),
            gas_max=self.gas.text.strip(),
            spent=self.total_spent,
            sigs=self.total_sigs)
        self.password = pwd

    def on_start(self, *_):
        pk = self.pk.text.strip()
        if not pk.startswith("0x") or len(pk) < 60:
            self.log("Invalid private key")
            return
        if not self.password:
            PasswordPopup(on_success=self._after_pwd, mode="set").open()
        else:
            self._go()

    def _after_pwd(self, pwd):
        self.save(pwd)
        self._go()

    def _go(self):
        self.mining = True
        self.start_btn.disabled = True
        self.stop_btn.disabled = False
        self.log("Mining started: 6 then 9, pause 6s, unique news per sig")
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def on_stop(self, *_):
        self.mining = False
        self.start_btn.disabled = False
        self.stop_btn.disabled = True
        self.log("Stopping after current batch...")
        if self.password:
            self.save(self.password)

    def _refresh_stats(self, address):
        try:
            st = rpcmod.stats_of(address)
            self.push_val = str(st.get("push", "-"))
            self.trust_val = str(st.get("trust", "-"))
            self.eff_val = str(st.get("effective", "-"))
            Clock.schedule_once(lambda d: self._upd_stats(), 0)
        except Exception as e:
            Clock.schedule_once(lambda d: self.log(f"Stats read failed: {str(e)[:50]}"), 0)

    def loop(self):
        try:
            pk_hex = self.pk.text.strip()
            priv_int = int(pk_hex.replace("0x", ""), 16)
            pub = privkey_to_pubkey(priv_int)
            signer = pubkey_to_address(pub)
            self.signer_addr = signer
            target = self.target.text.strip()
            self.log(f"Signer: {signer[:12]}...{signer[-8:]}")

            user_rpc = self.rpc.text.strip()
            if user_rpc:
                txmod.RPC_LIST = [user_rpc] + [u for u in txmod.RPC_LIST if u != user_rpc]
                try:
                    rpcmod.RPC_LIST = [user_rpc] + [u for u in getattr(rpcmod, "RPC_LIST", []) if u != user_rpc]
                except Exception:
                    pass

            try:
                gas_max_gwei = float(self.gas.text.strip() or DEFAULT_GAS_MAX)
            except Exception:
                gas_max_gwei = 1.5

            nonce = txmod.get_nonce(signer)
            self.log(f"Starting nonce: {nonce}")
            self._refresh_stats(signer)

            if not self.news_pool.titles:
                self.news_pool.refresh()

            while self.mining:
                for batch_size in (6, 9):
                    if not self.mining:
                        break

                    info = txmod.get_gas_price_info()
                    if info["gwei"] > gas_max_gwei:
                        src = info.get("source", "rpc")
                        self.log(f"Gas {info['gwei']:.3f} ({src}) > max {gas_max_gwei} - raise Gas max or wait")
                        Clock.schedule_once(
                            lambda d, g=info["gwei"], m=gas_max_gwei: setattr(
                                self.status_line, "text", f"Gas now {g:.2f} gwei (max {m}) - raise max to mint"
                            ), 0
                        )
                        time.sleep(12)
                        continue

                    src = info.get("source", "rpc")
                    self.log(f"Batch of {batch_size} | gas {info['gwei']:.3f} gwei ({src})")

                    for i in range(batch_size):
                        if not self.mining:
                            break
                        try:
                            meta = self.news_pool.next()[:64]
                            raw = f"sos24h-{signer.lower()}-{int(time.time())}-{nonce}-{i}".encode()
                            payload_hash = keccak256(raw)
                            sig = sign_record(priv_int, signer, target, payload_hash, meta)
                            sig_hex = "0x" + sig.hex()
                            ph_hex = "0x" + payload_hash.hex()

                            result = txmod.send_record_signature(
                                privkey_hex=pk_hex,
                                intended_to=target,
                                payload_hash=ph_hex,
                                signature_hex=sig_hex,
                                metadata=meta,
                                signer=signer,
                                nonce=nonce,
                                gas_price=info["wei"],
                            )
                            tx_hash = result["txHash"]
                            nonce += 1
                            self.total_sigs += 1
                            cost_est = result["gasLimit"] * result["gasPrice"] / 1e18
                            self.total_spent += cost_est

                            url = f"https://etherscan.io/tx/{tx_hash}"
                            self.log(f"OK #{self.total_sigs} [{meta[:32]}]", tx_url=url)
                            Clock.schedule_once(lambda d: self._upd_stats(), 0)
                            time.sleep(0.35)
                        except Exception as e:
                            self.log(f"Tx error: {str(e)[:80]}")
                            time.sleep(3)
                            try:
                                nonce = txmod.get_nonce(signer)
                            except Exception:
                                pass

                    # Refresh on-chain stats after each batch
                    self._refresh_stats(signer)

                if not self.mining:
                    break

                for sec in range(6, 0, -1):
                    if not self.mining:
                        break
                    Clock.schedule_once(lambda d, s=sec: setattr(self.status_line, "text", f"Pause {s}s ..."), 0)
                    time.sleep(1)
                Clock.schedule_once(
                    lambda d: setattr(self.status_line, "text", f"News pool: {len(self.news_pool.titles)} titles"), 0
                )

        except Exception as e:
            self.log(f"Fatal: {e}")
        finally:
            self.mining = False
            Clock.schedule_once(lambda d: self.on_stop(), 0)

    def _upd_stats(self):
        self.stats.text = (
            f"Push: {self.push_val} | Trust: {self.trust_val} | Effective: {self.eff_val}\n"
            f"Spent ~ {self.total_spent:.5f} ETH | Sigs: {self.total_sigs}"
        )
        if self.password:
            self.save(self.password)


class SOS69069App(App):
    def build(self):
        return MinerUI()


if __name__ == "__main__":
    SOS69069App().run()
