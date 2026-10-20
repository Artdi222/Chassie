# Chassie

Companion lokal dengan input Indonesia/Inggris, teks jawaban Inggris dan suara Jepang, kontrol percakapan browser, dan avatar Live2D. Runtime overlay sekarang menampilkan setengah badan dengan background transparan. Gunakan Python 3.12; lingkungan `.venv` sudah disiapkan pada mesin ini.

## Jalankan

Buka **Chassie** dari menu aplikasi. Launcher menyalakan backend lokal dan langsung menampilkan avatar; mikrofon mulai mati, sedangkan kamera dan pengamatan layar otomatis aktif. Klik avatar untuk membuka tombol chat, model/ekspresi, outfit, pengaturan, dan Stop. Seret avatar untuk memindahkannya. Menu tray menyediakan Keluar, hide/show, click-through, dan Buka web.

Web studio tersedia di `http://127.0.0.1:8000` selama aplikasi berjalan. Model tampil setengah badan, subtitle mengikuti kalimat yang sedang diucapkan, dan chat berada di kanan. Pilihan model dan penampilan tersinkron antara web dan desktop. Panel native memakai UI lokal yang sama; audio hanya diputar backend.

Satu-satunya model adalah Tian Muzi (`model/Model_4`). Pilih **Customize** untuk mencoba ekspresi dan gerak mulut. Model ini mendapat delapan preset ekspresi turunan (happy, sad, thinking, curious, surprised, angry, shy, sleepy), tanpa mengubah aset aslinya. Saat otomatis, ekspresi mengikuti jawaban serta status mendengar/berpikir dan kembali netral ketika idle. Matikan **Otomatis** untuk mengunci ekspresi manual. Zoom/framing desktop disimpan, dan panel pengaturan menyediakan Reset. Settings dibagi menjadi tab **Voice & chat**, **People & memory**, dan **System**.

Untuk menjalankan melalui terminal atau memasang ulang shortcut pada mesin ini:

```bash
.venv/bin/python launch.py
# Instal sekali jika Chassie belum ada di menu aplikasi:
install -Dm644 Chassie.desktop ~/.local/share/applications/chassie.desktop
```

Web saja, tanpa overlay:

```bash
.venv/bin/python start.py --text
```

UI dan tes model dapat dipakai tanpa Hermes; balasan percakapan memerlukan API Hermes aktif. Suara Jepang Ami/VOICEVOX dan teks terjemahan Inggris berjalan bersama. Lihat [setup Hermes](docs/hermes-setup.md).

Pada CachyOS/Hyprland, launcher memakai XWayland dan aturan khusus avatar agar transparan, selalu di atas, dan dipin lintas workspace. Panel kontrol tetap window biasa. Lihat [dukungan overlay](docs/overlay.md). Jika backend versi lama masih berjalan di terminal, hentikan dengan Ctrl+C sebelum membuka launcher baru.

## Perilaku yang perlu diketahui

- Tanpa gambar, jawaban memakai DeepSeek V4 Flash; dengan gambar yang diminta untuk pesan itu, memakai MiniMax M3 free. Routing memakai provider xKiro yang dikonfigurasi di Hermes, tanpa mengganti model global. `app_context.enabled` mengirim nama aplikasi aktif di Hyprland tanpa screenshot atau judul dokumen/tab, termasuk saat capture layar dimatikan. Matikan opsi tersebut untuk menonaktifkan metadata aplikasi. Saat chat/overlay Chassie mendapat fokus, metadata memakai aplikasi eksternal terakhir yang masih terbuka dari riwayat fokus Hyprland, disertai penanda bahwa aplikasi itu dipakai sebelum membuka chat.
- Jawaban Hermes diterima bertahap. Kalimat lengkap pertama langsung masuk TTS; satu kalimat berikutnya disiapkan selama playback. Subtitle mengikuti kalimat yang diucapkan. Teks bubble bertambah saat audio kalimat mulai diputar, termasuk saat chat tersambung ulang. Jika dihentikan, bubble ditandai interrupted; catatan kalimat yang selesai diucapkan tetap menunggu audio selesai. Provider harus mendukung SSE chat completions.
- Input `review` masuk sebagai draft; `hands_free` langsung dikirim. Mute menghentikan capture dan membatalkan transkripsi suara tertunda.
- Saat Chassie berbicara, mikrofon dijeda untuk mencegah suara speaker masuk kembali. Gunakan Stop untuk menyela. AEC dan interupsi otomatis melalui suara belum tersedia.
- Pemilik memory yang sudah dikonfigurasi dipakai otomatis. Perkenalkan wajah/suara melalui Memory & people setelah orang tersebut menyetujui; template disimpan lokal. Kehadiran orang lain menjeda konteks pribadi tanpa perlu mengelola profil atau tamu.
- Integrasi Femiris memakai provider memory native di Hermes. Header memory pribadi hanya dikirim ketika profil Artdi yang dikonfigurasi berada dalam scope personal. Mode tamu, profil tidak aktif, dan profil lain tidak mendapat akses ke vault Artdi melalui integrasi ini. Restart Chassie untuk menerapkan perubahan. Panduan dan verifikasi berada di proyek `/home/artdi/Projects/vector db/README.md`.
- Pertanyaan dan observasi sementara dikirim dalam satu pesan user agar normalisasi DeepSeek di Hermes mempertahankan hasil recall otomatis. Observasi tetap diberi label sebagai data, tidak masuk history Chassie, dan tidak disimpan sebagai fakta pengguna oleh Femiris.
- Kamera dan GUI layar diperbarui lokal setiap dua detik meskipun panel ditutup. Snapshot hanya dikirim saat diminta lewat teks atau suara, misalnya “lihat layar aku” atau “kamu bisa lihat aku?”. Permintaan berlaku untuk pesan itu saja dan hanya menyertakan sumber yang diminta. Status tampil di Settings → System. Lihat [pengamatan otomatis dan pengenalan wajah](docs/automatic-vision.md).
- Pemisahan memori ini mencakup state milik Chassie. Konteks, SOUL, memori, dan tools yang ditambahkan Hermes sendiri perlu konfigurasi terpisah sebelum menganggap percakapan tamu terisolasi sepenuhnya.
- TTS hanya memakai VOICEVOX Mochiko-san Normal. Model STT multilingual `base` memakai CPU/int8, dua thread; dukungan dua bahasa belum merupakan hasil benchmark akurasi percakapan campuran.

Log `Streaming turn timings` memisahkan teks pertama, kalimat pertama, PCM pertama, audio masuk antrean, stream selesai, dan playback selesai. Waktu masuk antrean bukan bukti saat suara terdengar dari speaker. Lihat [rencana dan verifikasi streaming](docs/superpowers/plans/2026-09-08-streaming-replies.md).

Jika web sempat thinking lalu kembali diam dengan pesan timeout: versi lama memakai batas tanpa data 30 detik, sama dengan interval keepalive Hermes. Batas ini kini 75 detik, dengan batas total stream tetap 180 detik; Stop tetap tersedia. Error respons tampil di area chat dan panel samping. Setelah memperbarui kode/config, hentikan backend dengan `Ctrl+C`, jalankan ulang `.venv/bin/python start.py --text`, lalu reload halaman web. Mengubah batas tunggu mencegah pemutusan prematur; tidak mempercepat model.

`hermes.reasoning_effort` di config Chassie sekarang `low` untuk percakapan singkat; gunakan `medium` untuk penalaran lebih mendalam atau `null` untuk mengikuti Hermes. Opsi diteruskan per request dan tidak mengubah reasoning CLI. Batas konteks alias/default di Hermes lokal sudah diatur untuk menghindari probe berulang. Waktu respons provider tetap bervariasi; hasil dan backup ada di [setup Hermes](docs/hermes-setup.md).

## Pengembangan dan tes

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest -q
.venv/bin/python tools/audit_avatar.py
```

Jangan menjalankan pembuatan `.venv` ulang bila sudah memakai environment yang disiapkan. Dependensi overlay bersifat opsional. Tes perangkat memakai fake stream; tes browser membuka server loopback sementara. [Evaluasi](evaluasi.md) memuat kasus lanjutan; [ledger implementasi](docs/superpowers/plans/2026-09-08-chassie-development.md) memisahkan hasil teruji dan pekerjaan tersisa.

## Japanese voice with English or Indonesian subtitles

The only voice is VOICEVOX Mochiko-san Normal. Input supports Indonesian or English; speech is Japanese and reply chat/subtitles are English or Indonesian (Settings → Voice & chat → Subtitle & chat language; saved in `.chassie/speech-settings.json`, default `tts.translation_language: en`). On a fresh checkout, run `.venv/bin/python scripts/install_voicevox.py` once, then launch Chassie normally. See [VOICEVOX setup and voice credits](docs/voicevox.md).

Interaksi mouse: kursor pada avatar atau sekitar 180 piksel logis dari bagian yang terlihat mengarahkan tatapan, tanpa harus menyentuh tubuh/rambut. Melewati batas kedekatan ini melepas target kursor, lalu tatapan bertransisi ke idle. Area kedekatan mengikuti bagian model, bukan seluruh panel transparan. Hover singkat di bagian kepala memicu headpat lembut (menunduk, memejamkan mata, tersenyum), lalu kembali ke ekspresi pilihan ketika kursor menjauh. Tepi kepala memiliki toleransi dan jeda keluar singkat agar gerakan kepala atau kursor kecil tidak membuat ekspresi berkedip. Drag tetap memindahkan avatar. Ini berjalan lokal di renderer desktop dan browser, tanpa kamera atau panggilan model AI.

Scrollbar chat disembunyikan; riwayat tetap bisa digulir dengan roda mouse atau touchpad. Pengujian visual dan interaksi saat ini difokuskan ke Model_4.


## Memory dan pengenalan orang

Dengan `companion.automatic_memory: true`, profil pemilik yang sudah dikonfigurasi dipakai otomatis. **Memory & people** menampilkan vault Femiris yang juga dipakai Hermes (`/home/artdi/Documents/Memory`), sehingga tidak perlu memilih profil atau mengelola tamu. Fakta/preferensi eksplisit tetap ditangkap oleh Hermes dan sinkronisasi yang sudah diaktifkan; dugaan dan hasil pengenalan wajah/suara tidak dijadikan fakta personal. Catatan buatan tangan diedit di Obsidian; fakta yang dikelola Femiris bisa diedit/dihapus dari panel.

Gunakan **Introduce someone** sekali untuk diri sendiri atau orang lain yang sudah menyetujui. Pilih wajah (sendirian menghadap kamera) dan/atau suara (ucapkan 3–12 detik setelah menekan Remember). Perkenalan suara berlaku 90 detik, bisa dibatalkan, dan sampelnya tidak dikirim sebagai pesan chat. Setelah tersimpan, pengenalan berjalan otomatis. **Forget face & voice** menghapus kedua template tanpa menghapus catatan teks.

Template ArcFace dan WeSpeaker berada di SQLite lokal `.chassie/memory.sqlite`; rekaman/foto tidak disimpan ke vault maupun dikirim untuk embedding memory. Speaker runtime memakai Sherpa-ONNX CPU. Pada instalasi baru jalankan `.venv/bin/python scripts/install_speaker.py`; model ResNet34 VoxCeleb berlisensi [CC BY 4.0 menurut WeSpeaker](https://github.com/wenet-e2e/wespeaker/blob/master/docs/pretrained.md#model-license), dengan checksum dari [artefak maintainer](https://huggingface.co/csukuangfj/speaker-embedding-models/blob/main/wespeaker_en_voxceleb_resnet34.onnx).

Pengenalan adalah perkiraan, bukan autentikasi. Orang tambahan atau suara yang tidak cocok menghentikan konteks pribadi. Kehadiran wajah pemilik sendirian selama 5 detik dapat memulihkan jeda akibat kamera. Jika jeda akibat suara belum jelas, **I'm alone · resume my memories** memulihkan lewat tindakan pemilik di komputer ini. Tidak ada pergantian pemilik otomatis berdasarkan kemiripan wajah/suara. Kalibrasi akurasi orang sungguhan memerlukan perkenalan dan uji mikrofon/kamera di perangkat pengguna.

**Customize → Mouse & headpat** menyimpan jarak kedekatan (40–400 px), kecepatan mengikuti, jeda headpat, dan toggle masing-masing. Chat mempertahankan posisi saat membaca pesan lama; **New messages ↓** melompat ke jawaban terbaru. Setiap bubble menyediakan Copy, dan jawaban gagal menyediakan Try again untuk pertanyaan asli.

