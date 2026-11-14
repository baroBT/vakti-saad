from datetime import datetime, timedelta
import math, random, threading, json, os

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.lang import Builder
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.properties import StringProperty, BooleanProperty
from kivy.storage.jsonstore import JsonStore

try:
    import requests
except:
    requests = None

try:
    from plyer import notification
except:
    notification = None

SEHIRLER = {
    "İstanbul": (41.0082, 28.9784), "Ankara": (39.9334, 32.8597),
    "İzmir": (38.4237, 27.1428), "Bursa": (40.1885, 29.0610),
    "Antalya": (36.8969, 30.7133), "Konya": (37.8746, 32.4932),
    "Adana": (37.0, 35.3213), "Gaziantep": (37.0662, 37.3833),
    "Şanlıurfa": (37.1591, 38.7969), "Diyarbakır": (37.9144, 40.2306),
    "Kayseri": (38.7312, 35.4787), "Samsun": (41.2867, 36.33),
    "Trabzon": (41.0015, 39.7178), "Erzurum": (39.9043, 41.2679),
    "Van": (38.4891, 43.4089), "Mersin": (36.8, 34.6333),
    "Eskişehir": (39.7767, 30.5206), "Muğla": (37.2153, 28.3636),
}

AYETLER = [
    "Şüphesiz Allah, sabredenlerle beraberdir. - Bakara 153",
    "Kalpler ancak Allah'ı anmakla huzur bulur. - Rad 28",
    "Allah, hiç kimseye gücünün üstünde yük yüklemez. - Bakara 286",
    "Her zorlukla beraber bir kolaylık vardır. - İnşirah 5",
    "Rabbin seni terk etmedi, sana darılmadı da. - Duha 3",
]

CACHE_DOSYA = "vakit_cache.json"

# ---------- OFFLINE HESAP (temkinli, Diyanet'e yakın) ----------
def vakitleri_hesapla_offline(enlem, boylam, tarih=None):
    if tarih is None:
        tarih = datetime.now()
    N = tarih.timetuple().tm_yday
    decl = -23.44 * math.cos(math.radians(360/365 * (N + 10)))
    decl_rad = math.radians(decl)
    lat_rad = math.radians(enlem)
    ogle_saat = 12 + (30 - boylam) / 15 * -1

    def saat_hesapla(aci):
        cos_h = (math.sin(math.radians(aci)) - math.sin(lat_rad)*math.sin(decl_rad)) / (math.cos(lat_rad)*math.cos(decl_rad))
        cos_h = max(-1, min(1, cos_h))
        return math.degrees(math.acos(cos_h)) / 15

    def yap(saat_float):
        h = int(saat_float)
        m = int((saat_float - h) * 60)
        if m >= 60: h += 1; m -= 60
        if m < 0: h -= 1; m += 60
        return tarih.replace(hour=h % 24, minute=m, second=0, microsecond=0)

    gunes_h = saat_hesapla(-0.833)
    imsak_h = saat_hesapla(-18)
    yatsi_h = saat_hesapla(-17)

    # Temkin değerleri (dakika) - Diyanet'e yaklaştırır
    imsak = yap(ogle_saat - imsak_h)
    gunes = yap(ogle_saat - gunes_h) - timedelta(minutes=7)
    ogle = yap(ogle_saat + 0.08) + timedelta(minutes=5)
    ikindi = yap(ogle_saat + gunes_h * 0.55 + 0.3) + timedelta(minutes=4)
    aksam = yap(ogle_saat + gunes_h) + timedelta(minutes=7)
    yatsi = yap(ogle_saat + yatsi_h)

    return {
        "İmsak": imsak, "Güneş": gunes, "Öğle": ogle,
        "İkindi": ikindi, "Akşam": aksam, "Yatsı": yatsi,
    }

# ---------- ALADHAN (online, Diyanet method=13) ----------
def aladhan_cek(sehir, tarih=None):
    if requests is None:
        return None
    if tarih is None:
        tarih = datetime.now()
    try:
        url = (
            f"https://api.aladhan.com/v1/timingsByCity/"
            f"{tarih.strftime('%d-%m-%Y')}"
            f"?city={sehir}&country=Turkey&method=13"
        )
        r = requests.get(url, timeout=8)
        data = r.json()
        t = data["data"]["timings"]
        def parse(s):
            s = s.split(" ")[0]
            h, m = s.split(":")
            return tarih.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        return {
            "İmsak": parse(t["Fajr"]), "Güneş": parse(t["Sunrise"]),
            "Öğle": parse(t["Dhuhr"]), "İkindi": parse(t["Asr"]),
            "Akşam": parse(t["Maghrib"]), "Yatsı": parse(t["Isha"]),
        }
    except Exception as e:
        print("Aladhan hata:", e)
        return None

def cache_yaz(sehir, vakitler):
    try:
        data = {"sehir": sehir, "tarih": datetime.now().strftime("%Y-%m-%d"),
                "vakitler": {k: v.strftime("%H:%M") for k, v in vakitler.items()}}
        with open(CACHE_DOSYA, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print("Cache yaz hata:", e)

def cache_oku(sehir):
    try:
        if not os.path.exists(CACHE_DOSYA):
            return None
        with open(CACHE_DOSYA) as f:
            data = json.load(f)
        if data.get("sehir") != sehir:
            return None
        bugun = datetime.now()
        return {
            k: bugun.replace(hour=int(v.split(":")[0]), minute=int(v.split(":")[1]), second=0, microsecond=0)
            for k, v in data["vakitler"].items()
        }
    except:
        return None

def kible_acisi(enlem, boylam):
    lat1 = math.radians(enlem); lon1 = math.radians(boylam)
    lat2 = math.radians(21.4225); lon2 = math.radians(39.8262)
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1)*math.sin(lat2) - math.sin(lat1)*math.cos(lat2)*math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

def bildirim_gonder(baslik, mesaj):
    if notification:
        try:
            notification.notify(title=baslik, message=mesaj, app_name="Vakt-i Saad", timeout=5)
        except Exception as e:
            print(e)

# ---------- RAMAZAN (yaklaşık hicri hesap) ----------
def ramazan_durumu():
    """Ramazan ayında mıyız, kaç gün kaldı? (yaklaşık hesap)"""
    simdi = datetime.now()
    # Hicri yıl yaklaşık: (miladi - 622) * 33/32
    hicri_yil = int((simdi.year - 622) * 33 / 32)
    # 1 Ramazan yaklaşık tarihi (her yıl 11 gün geri gelir)
    # 2026 Ramazan: ~18 Şubat 2026 (yaklaşık)
    ramazan_baslangic = datetime(simdi.year, 2, 18)  # yaklaşık
    if simdi.month < 2 or (simdi.month == 2 and simdi.day < 18):
        ramazan_baslangic = datetime(simdi.year - 1, 3, 1)
    ramazan_bitis = ramazan_baslangic + timedelta(days=30)
    if ramazan_baslangic <= simdi <= ramazan_bitis:
        gun = (simdi - ramazan_baslangic).days + 1
        return True, gun, 0
    else:
        if simdi < ramazan_baslangic:
            kalan = (ramazan_baslangic - simdi).days
        else:
            yeni = ramazan_baslangic.replace(year=ramazan_baslangic.year + 1) - timedelta(days=11)
            kalan = (yeni - simdi).days
        return False, 0, kalan

Builder.load_string("""
<AnaEkran>:
    orientation: "vertical"
    padding: 15
    spacing: 6
    canvas.before:
        Color:
            rgba: (0.05, 0.05, 0.1, 1) if root.karanlik else (0.95, 0.95, 0.95, 1)
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        text: root.sehir_text
        font_size: "15sp"
        color: (1,1,1,1) if root.karanlik else (0,0,0,1)
        size_hint_y: 0.06
    Label:
        text: root.kaynak_text
        font_size: "10sp"
        color: (0.5,0.8,0.5,1)
        size_hint_y: 0.03
    Label:
        text: root.sonraki_ad
        font_size: "24sp"
        bold: True
        color: (0.2, 0.8, 0.4, 1)
        size_hint_y: 0.1
    Label:
        text: root.kalan_sure
        font_size: "38sp"
        bold: True
        color: (1,1,1,1) if root.karanlik else (0,0,0,1)
        size_hint_y: 0.14
    Label:
        text: root.ramazan_text
        font_size: "13sp"
        color: (1, 0.8, 0.2, 1)
        size_hint_y: 0.05
    BoxLayout:
        orientation: "vertical"
        size_hint_y: 0.3
        ScrollView:
            BoxLayout:
                id: vakit_listesi
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                spacing: 2
    Label:
        text: root.hicri
        font_size: "12sp"
        color: (0.7,0.7,0.7,1)
        size_hint_y: 0.04
    Label:
        text: root.ayet
        font_size: "11sp"
        color: (0.6,0.6,0.6,1)
        size_hint_y: 0.07
        text_size: self.width, None
        halign: "center"
    Label:
        text: "Vakt-i Saad | Baro-BT Studios"
        font_size: "10sp"
        color: (0.5,0.5,0.5,1)
        size_hint_y: 0.03
    BoxLayout:
        size_hint_y: 0.11
        spacing: 5
        Button:
            text: "Şehir"
            on_press: root.sehir_sec()
        Button:
            text: "Tema"
            on_press: root.tema_degistir()
        Button:
            text: "Kıble"
            on_press: root.kible_goster()
        Button:
            text: "Yenile"
            on_press: root.veri_cek()
""")

class AnaEkran(BoxLayout):
    sehir_text = StringProperty("")
    kaynak_text = StringProperty("")
    sonraki_ad = StringProperty("")
    kalan_sure = StringProperty("")
    hicri = StringProperty("")
    ayet = StringProperty("")
    ramazan_text = StringProperty("")
    karanlik = BooleanProperty(True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.vakitler = {}
        self.son_bildirim = ""
        Clock.schedule_interval(self.guncelle, 1)
        Clock.schedule_once(self.ilk_yukle, 0.5)

    def ilk_yukle(self, dt):
        app = App.get_running_app()
        self.sehir_text = f"📍 {app.ayar.get('sehir', 'İstanbul')}"
        self.karanlik = app.ayar.get('karanlik', True)
        self.ayet = random.choice(AYETLER)
        self.veri_cek()

    def veri_cek(self):
        app = App.get_running_app()
        sehir = app.ayar.get("sehir", "İstanbul")
        self.kaynak_text = "Yükleniyor..."
        cached = cache_oku(sehir)
        if cached:
            self.vakitler = cached
            self.vakit_listesi_guncelle()
            self.kaynak_text = "Önbellekten (internet bekleniyor)"
        threading.Thread(target=self._online_cek, args=(app.enlem, app.boylam, sehir), daemon=True).start()

    def _online_cek(self, enlem, boylam, sehir):
        v = aladhan_cek(sehir)
        if v:
            cache_yaz(sehir, v)
            self._online_basarili(v)
        else:
            v = vakitleri_hesapla_offline(enlem, boylam)
            self._offline_basarili(v)

    @mainthread
    def _online_basarili(self, v):
        self.vakitler = v
        self.vakit_listesi_guncelle()
        self.kaynak_text = "🌐 Aladhan (Diyanet method=13)"

    @mainthread
    def _offline_basarili(self, v):
        self.vakitler = v
        self.vakit_listesi_guncelle()
        self.kaynak_text = "📴 Offline hesap (temkinli)"

    def vakit_listesi_guncelle(self):
        container = self.ids.vakit_listesi
        container.clear_widgets()
        for ad, saat in self.vakitler.items():
            lbl = Label(text=f"{ad}: {saat.strftime('%H:%M')}", font_size="16sp",
                        color=(1,1,1,1) if self.karanlik else (0,0,0,1),
                        size_hint_y=None, height=32)
            container.add_widget(lbl)

    def guncelle(self, dt):
        if not self.vakitler:
            return
        simdi = datetime.now()
        siradaki = None
        for ad, saat in self.vakitler.items():
            if saat > simdi:
                siradaki = (ad, saat)
                break
        if siradaki is None:
            yarin = simdi + timedelta(days=1)
            yarin_v = vakitleri_hesapla_offline(App.get_running_app().enlem, App.get_running_app().boylam, yarin)
            siradaki = ("İmsak", yarin_v["İmsak"])

        ad, saat = siradaki
        self.sonraki_ad = f"{ad} vaktine"
        kalan = saat - simdi
        if kalan.total_seconds() < 0:
            kalan = timedelta(0)
        h = int(kalan.total_seconds() // 3600)
        m = int((kalan.total_seconds() % 3600) // 60)
        s = int(kalan.total_seconds() % 60)
        self.kalan_sure = f"{h:02d}:{m:02d}:{s:02d}"

        if self.son_bildirim != f"{ad}_geldi" and abs(kalan.total_seconds()) < 2:
            bildirim_gonder(f"{ad} Vakti", f"{ad} vakti geldi.")
            self.son_bildirim = f"{ad}_geldi"

        # Ramazan
        oruç, gun, kalan_gun = ramazan_durumu()
        if oruç:
            if ad == "İmsak" or (ad == "Akşam"):
                pass
            # İmsak/iftar sayacı
            if simdi < self.vakitler["İmsak"]:
                self.ramazan_text = f"🌙 Sahura {self.kalan_sure_hesapla(self.vakitler['İmsak'])} kaldı (Ramazan {gun}. gün)"
            elif simdi < self.vakitler["Akşam"]:
                self.ramazan_text = f"🌙 İftara {self.kalan_sure_hesapla(self.vakitler['Akşam'])} kaldı (Ramazan {gun}. gün)"
            else:
                self.ramazan_text = f"🌙 Ramazan {gun}. gün | Yarın imsak: {self.vakitler['İmsak'].strftime('%H:%M')}"
        else:
            self.ramazan_text = f"🌙 Ramazan'a {kalan_gun} gün kaldı"

        self.hicri = f"Miladi: {simdi.strftime('%d.%m.%Y')} | Hicri (yaklaşık): {simdi.year - 622}"

    def kalan_sure_hesapla(self, hedef):
        kalan = hedef - datetime.now()
        if kalan.total_seconds() < 0:
            return "0 dk"
        h = int(kalan.total_seconds() // 3600)
        m = int((kalan.total_seconds() % 3600) // 60)
        return f"{h} saat {m} dk"

    def sehir_sec(self):
        icerik = BoxLayout(orientation="vertical", spacing=10, padding=10)
        spinner = Spinner(text="Şehir seç", values=list(SEHIRLER.keys()), size_hint_y=0.3)
        icerik.add_widget(spinner)
        btn = Button(text="Tamam", size_hint_y=0.3)
        icerik.add_widget(btn)
        popup = Popup(title="Şehir Seç", content=icerik, size_hint=(0.8, 0.5))

        def sec(instance):
            app = App.get_running_app()
            secilen = spinner.text
            if secilen in SEHIRLER:
                app.enlem, app.boylam = SEHIRLER[secilen]
                app.ayar["sehir"] = secilen
                app.kaydet()
                self.sehir_text = f"📍 {secilen}"
                self.veri_cek()
            popup.dismiss()

        btn.bind(on_press=sec)
        popup.open()

    def tema_degistir(self):
        app = App.get_running_app()
        self.karanlik = not self.karanlik
        app.ayar["karanlik"] = self.karanlik
        app.kaydet()
        self.vakit_listesi_guncelle()

    def kible_goster(self):
        app = App.get_running_app()
        aci = kible_acisi(app.enlem, app.boylam)
        metin = f"Şehrin: {app.ayar.get('sehir','İstanbul')}\nKıble Açısı: {aci:.0f}°\n\nTelefonu kuzeye çevir,\n{aci:.0f} derece sağa dön."
        Popup(title="Kıble", content=Label(text=metin), size_hint=(0.85, 0.55)).open()

class VaktiSaadApp(App):
    enlem = 41.0082
    boylam = 28.9784

    def build(self):
        self.title = "Vakt-i Saad"
        self.ayar_dosyasi = JsonStore("vakti_saad_ayar.json")
        self.ayar = {
            "sehir": self.ayar_dosyasi.get("sehir")["deger"] if self.ayar_dosyasi.exists("sehir") else "İstanbul",
            "karanlik": self.ayar_dosyasi.get("karanlik")["deger"] if self.ayar_dosyasi.exists("karanlik") else True,
        }
        if self.ayar["sehir"] in SEHIRLER:
            self.enlem, self.boylam = SEHIRLER[self.ayar["sehir"]]

        sm = ScreenManager(transition=FadeTransition(duration=1.0))
        splash = Screen(name="splash")
        splash_box = BoxLayout(orientation="vertical", padding=40)
        splash_box.add_widget(Label(text="Baro-BT Studios", font_size="22sp"))
        splash_box.add_widget(Label(text="Vakt-i Saad", font_size="34sp", bold=True, color=(0.2,0.8,0.4,1)))
        splash_box.add_widget(Label(text="Namaz Vakitleri", font_size="16sp"))
        splash.add_widget(splash_box)
        sm.add_widget(splash)

        ana = Screen(name="ana")
        ana.add_widget(AnaEkran())
        sm.add_widget(ana)

        Clock.schedule_once(lambda dt: setattr(sm, "current", "ana"), 2)
        return sm

    def kaydet(self):
        for k, v in self.ayar.items():
            self.ayar_dosyasi.put(k, deger=v)

if __name__ == "__main__":
    VaktiSaadApp().run()
