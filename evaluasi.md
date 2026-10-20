# Evaluasi Pengembangan Chassie

Pembaruan: 8 September 2026.

Status: arah pengembangan telah disetujui untuk implementasi bertahap. Fondasi percakapan, memori lokal manual, mapping ekspresi, dan overlay telah diimplementasikan; bukti serta batasnya dicatat di bagian 1.2. Uraian baseline pada bagian 2 adalah snapshot **sebelum** implementasi. Skenario lanjutan tidak otomatis berarti fitur sudah selesai.

## 1. Keputusan pengguna

| Topik | Keputusan / status |
| --- | --- |
| Interaksi | Personal + tamu: fokus pada pemilik; teman dapat bergabung setelah diizinkan. |
| Ingatan identitas | Profil wajah/suara lokal, opt-in, dapat bertahan lintas sesi. Orang yang tidak mendaftar tetap tamu sementara. |
| Perangkat | GPU 4 GB VRAM, RAM 8 GB. Baseline diuji pada CachyOS/Linux lewat XWayland; dukungan Windows belum diuji. |
| Audio utama | Speaker dan satu mikrofon bersama untuk pemilik dan tamu. |
| TTS | Pertahankan suara Inggris saat ini. Pengguna sudah mencoba Edge TTS Indonesia dan tidak menyukai hasilnya; jangan merekomendasikannya kembali. |
| Bahasa input | Indonesia + Inggris; output TTS tetap Inggris. |
| Runtime avatar | Runtime Cubism mandiri sudah berhasil merender model asli; VTS tetap tersedia. Belum ada klaim kualitas/performa melebihi VTS. |
| Tampilan desktop | Overlay transparan kanan bawah, framing setengah badan dengan wajah besar; zoom dan framing bisa diatur terpisah dari ukuran window. |
| Pekerjaan saat ini | Implementasi bertahap dan tes telah diizinkan. Aset asli di folder model tetap dipertahankan. |

Kesimpulan desain sementara: Chassie memerlukan pengaturan giliran, identitas peserta, dan pemisahan konteks personal/tamu. Mengganti model vision atau runtime avatar saja tidak menyelesaikan kasus percakapan sehari-hari.

### 1.1 Arah tambahan yang diterima dalam diskusi

Pengguna menerima arah pengembangan berikut secara umum. Detail perilaku, prioritas final, dan implementasinya masih dibahas.

- Mode fokus, santai, dan tamu. Fokus membatasi percakapan spontan, bukan diam-diam mematikan mikrofon. Default awal yang diusulkan adalah fokus.
- Ingatan topik aktif, pertanyaan tertunda, serta bagian jawaban yang terinterupsi agar “lanjut tadi” dapat ditangani; klarifikasi jika rujukannya ambigu.
- Perilaku avatar untuk mendengarkan, memproses, berbicara, terinterupsi, menunggu, dan tidak yakin. Transisi mengikuti kejadian percakapan, bukan perubahan emosi acak.
- Panel memori yang memperlihatkan isi, sumber, serta kontrol koreksi/hapus. Preferensi jangka panjang diusulkan disimpan melalui permintaan atau persetujuan pengguna.
- Koreksi melalui percakapan, seperti “itu temanku yang ngomong”, “aku belum selesai”, dan “lupakan tadi”, perlu mengubah state terkait, bukan sekadar menghasilkan balasan setuju.
- Studio preview ekspresi untuk mencoba emosi + FX, lip-sync, neutral, serta kombinasi outfit tanpa bergantung pada respons Hermes.
- Longgarkan instruksi prompt yang sekarang meminta 2–4 perubahan emosi setiap jawaban biasa. Banyaknya transisi mengikuti makna kalimat dan kebutuhan karakter.

Bahasa input serta kapasitas perangkat kini sudah dikonfirmasi. Penggunaan utama dan tingkat keaktifan spontan masih perlu dipilih.

### 1.2 Hasil implementasi dan batas verifikasi

- Capture/STT terpisah, antrean terbatas, epoch untuk menolak transkripsi lama setelah mute/clear. Bahasa otomatis memakai Whisper multilingual base CPU/int8, dua thread untuk anggaran perangkat ini.
- Stop membatalkan buffer audio perangkat, tugas TTS, dan output avatar generasi lama. Kalimat berikutnya disintesis ketika kalimat sekarang diputar; riwayat interupsi hanya mencatat kalimat yang selesai diputar.
- UI review/hands-free, mute, Stop, lanjut topik, focus/casual, profil manual, serta memori consent/edit/delete. Tamu menangguhkan konteks personal lokal. Observasi beberapa wajah memicu penangguhan; identitas wajah dan suara belum diverifikasi otomatis.
- Mapping 16 emosi memakai file ekspresi eksplisit dan inventaris runtime. Reset neutral mempertahankan outfit. Audit aset memiliki nol error dan empat warning yang didokumentasikan; kombinasi visual tertentu tetap perlu dinilai pengguna.
- Overlay Cubism asli berhasil dirender, termasuk alpha transparan; framing setengah badan diverifikasi dengan screenshot. Kontrol zoom/framing/resize/hide dan flag click-through diuji. Pengiriman klik ke aplikasi lain, Windows, native Wayland, serta parity VTS belum diverifikasi.
- TTS Inggris berhasil menghasilkan PCM lewat layanan Edge. Tes deterministik dan browser memakai data sintetis. Latency akustik speaker/mikrofon, akurasi input campuran, serta sesi panjang belum diukur.
- Interupsi otomatis lewat suara, AEC, pengenalan wajah/suara, active-speaker attribution, capture layar/VLM, dan koreksi identitas lewat ucapan masih pekerjaan lanjutan. Saat audio diputar, capture mikrofon dijeda secara eksplisit; jangan menyebutnya full-duplex.
- Isolasi memori teruji untuk data yang dikelola Chassie. Hermes dapat menambahkan SOUL/memori/tools sendiri; isolasi backend tersebut belum dibuktikan. API Hermes sudah diaktifkan di localhost dengan key privat dan service berhasil direstart setelah persetujuan. Health/auth lulus; tes jawaban terhambat kuota gratis model deepseek-v4-flash-free (HTTP 429). Kegagalan provider yang dibungkus sebagai teks jawaban kini ditolak sebelum riwayat/TTS. Total 83 tes lulus setelah perbaikan ini.

Detail perintah, bukti, dan status terbaru ada di [ledger implementasi](docs/superpowers/plans/2026-09-08-chassie-development.md), [runtime overlay](docs/overlay.md), dan [setup Hermes](docs/hermes-setup.md).

Tes ulang setelah pengguna mengganti model Hermes menjadi `Combo_AI`: health tetap lulus, tetapi percakapan pertama gagal di provider dan satu percobaan ulang timeout pada batas 30 detik. Jawaban valid dan TTS dari model baru belum terverifikasi; penyebabnya belum dipastikan sama dengan kuota model lama.

Perbaikan Hyprland/Caelestia: overlay kini mendaftarkan aturan runtime khusus class/title avatar agar floating, pinned lintas workspace, tanpa blur/shadow/border dari compositor. Status tersebut diverifikasi pada window asli Hyprland 0.56.2 setelah hide/show, resize dan perubahan click-through; panel kontrol tidak ikut pinned. Tidak ada perubahan konfigurasi global Caelestia. Restart overlay setelah reload konfigurasi Hyprland untuk mendaftarkan ulang aturan. Perilaku di atas game fullscreen belum diuji.

Peningkatan latency berikutnya sudah diimplementasikan: teks Hermes diterima melalui SSE dan kalimat lengkap pertama langsung masuk TTS, tanpa menunggu seluruh respons selesai. Antrean teks dibatasi delapan segmen dan prefetch satu kalimat; tag emosi diproses lintas paket. Teks browser diperbarui pada satu bubble. Tes HTTP lokal membuktikan playback pertama dimulai saat stream masih terbuka, dengan perangkat output palsu. **138 tes lulus** setelah perbaikan pembatalan mikrofon dan privasi stream. Tes streaming awal gagal di provider Hermes; percobaan diagnosis berikutnya berhasil, tetapi belum membuktikan percepatan respons nyata. Detail di [verifikasi streaming](docs/superpowers/plans/2026-09-08-streaming-replies.md).

Diagnosis keluhan “thinking lama dibanding CLI” menemukan teks pertama dari gateway pada 22,839 detik: sekitar 15,8 detik persiapan sebelum panggilan model 7,0 detik. Log persiapan mencatat deteksi context length `Combo_AI` gagal berulang. API membuat agent baru per permintaan; probe gagal tidak masuk cache positif. Pengguna memakai round-robin, sehingga model yang melayani request juga bervariasi. Prioritas berikutnya adalah menetapkan batas konteks yang valid untuk seluruh anggota rute dan menghindari probe berulang; konfigurasi belum diubah. Tes ini tanpa TTS/audio dan CLI belum dibandingkan secara terkontrol. [Bukti dan batas diagnosis](docs/hermes-setup.md).

Tes ulang setelah pengguna mengganti routing menjadi fallback (14:09 WIB): alias yang teramati sekarang `hermes`, jawaban sintetis tepat dan stream selesai bersih. Teks pertama 34,248 detik; panggilan model 19,5 detik dan sisa persiapan/transport sekitar 14,8 detik. Deteksi context length masih gagal dua kali dan override belum terisi. Satu sampel ini belum menunjukkan perbaikan; model upstream dan jumlah input token belum dikontrol untuk perbandingan. Pengukuran tidak melibatkan TTS/audio.

Perbaikan web “thinking lalu berhenti tanpa jawaban”: pengguna mengonfirmasi error timeout. Ditemukan batas tanpa data Chassie 30 detik berlomba dengan interval keepalive Hermes 30 detik. Batas dinaikkan menjadi 75 detik dengan total tetap 180 detik dan Stop tetap aktif. Error kini muncul di percakapan, termasuk saat sidebar mobile tertutup. Tiga regresi direproduksi sebelum fix; seluruh **142 tes lulus** setelah fix. Ini memperbaiki koneksi yang diputus terlalu awal, bukan mempercepat inferensi. Backend Chassie perlu dijalankan ulang dan browser direload.

Verifikasi langsung lewat WebSocket Chassie terisolasi → Hermes nyata → TTS Inggris nyata berhasil: teks pertama 14,185 detik, PCM pertama 15,100 detik. Memori sementara dan perangkat output palsu dipakai; tidak ada rekaman atau suara speaker. Angka ini satu sampel, bukan klaim percepatan model. Bukti: `.test-artifacts/web-turn-live-check.json`.

Perbaikan latensi berikutnya sudah diterapkan di `~/.hermes/config.yaml` setelah izin pengguna: batas konteks default dan alias `9router/hermes` 131.072 token. Alias router saat diperiksa hanya menunjuk `gemini/gemini-3.8-flash`; katalog lokal mencatat kapasitas 1.048.576 token. Kedua probe yang gagal hilang; persiapan agent setelah cache hangat sekitar 0,12–0,13 detik. Reasoning `low` dikirim khusus request Chassie, sedangkan CLI tetap mengikuti global `medium`. **143 tes lulus**; loader asli Hermes diuji tanpa jaringan dan pembatasan alias/endpoint terverifikasi. Teks pertama pada dua tes low masih bervariasi 6,334 dan 19,889 detik; log terakhir menempatkan 19,5 detik di panggilan model. Belum ada bukti kecepatan stabil 1–2 detik. [Detail konfigurasi, backup, dan seluruh sampel](docs/hermes-setup.md).

## 2. Snapshot baseline sebelum implementasi dan koreksi evaluasi lama

Alur yang ditemukan pada pemeriksaan awal:

```text
Mic → WebRTC VAD → faster-whisper → antrean teks
                                      ↓
                          UI review / kirim langsung
                                      ↓
FaceTracker → string ekspresi → HermesBridge
                                      ↓
                     respons lengkap + emotion parser
                                      ↓
                       Edge TTS → antrean AudioPlayer
                                      ↓
                        audio + ekspresi/lip-sync VTS
```

| Area | Temuan source | Implikasi |
| --- | --- | --- |
| Kamera | FaceTracker memakai RunningMode.IMAGE, num_faces=1, mengambil face_blendshapes[0], interval konfigurasi 0,5 detik. | Belum ada identitas, track peserta stabil, atau penguncian wajah pemilik. Urutan hasil bukan identitas. |
| Konteks wajah | get_context_string() menghasilkan string seperti “User is smiling”. | Tidak membawa peserta, kualitas, atau timestamp. Wajah orang lain dapat salah dikaitkan ke ucapan pemilik. |
| Kamera gagal | Kegagalan membaca frame melewati pembaruan ekspresi. | Nilai sebelumnya dapat bertahan; diperlukan status unavailable dan kedaluwarsa observasi. |
| Ekspresi pengguna | tired/laughing dan kategori lain berasal dari threshold blendshape. | Petunjuk visual yang bisa salah, bukan kepastian kondisi batin. |
| STT | Output hanya teks, tanpa identitas pembicara atau timestamp segmen yang diteruskan. | Semua pembicara berpotensi dianggap user yang sama. |
| Capture audio | Transkripsi dipanggil pada thread yang juga membaca mikrofon. | Pembacaan tertunda selama inference; perlu capture terpisah dan buffer terbatas. |
| Bahasa | Model base.en, language="en", voice en-US-AnaNeural. | Input Indonesia belum didukung konfigurasi sekarang; keputusan STT terpisah dari preferensi TTS Inggris. |
| Endpointing | Silence tetap 1,5 detik. vad_threshold dibaca, tetapi VAD memakai aggressiveness tetap 2. | Jangan menganggap perubahan threshold konfigurasi tersebut sudah mengubah perilaku VAD. |
| Filter STT | Frasa seperti “thank you” dan hasil sangat pendek dibuang. | Bisa menghapus ucapan valid; respons singkat dan perintah stop perlu diuji. |
| Mute UI | Toggle hanya menampilkan pemberitahuan. | Belum mematikan capture di backend. |
| Routing STT | Browser terhubung: masuk textbox. Tanpa browser: langsung dikirim. | Mode review/hands-free harus eksplisit, bukan berubah karena koneksi UI. |
| Hermes | Respons dibaca lengkap. | Sentence chunking setelah respons lengkap tidak mengurangi waktu generasi Hermes. Streaming gateway belum diverifikasi. |
| Riwayat | Satu daftar pesan dalam RAM; jawaban lengkap disimpan sebelum selesai diucapkan. | Belum ada memori persisten, pemisahan peserta, atau pencatatan jawaban yang terinterupsi. |
| TTS | Menyimpan file sementara berakhiran .wav, membaca seluruh audio, lalu yield satu array. | Belum streaming PCM bertahap. Ekstensi tidak membuktikan WAV; Edge mengirim MP3. |
| Playback | Sudah memakai background thread; segmen berikutnya bisa disintesis saat segmen sebelumnya diputar. | Perbaiki buffering/backpressure; jangan membangun ulang konkurensi yang sudah ada. |
| Pembatalan | stop() menghentikan thread; clear_queue() tidak menghapus buffer aktif atau membatalkan produsen. | Perlu pembatalan ucapan yang mempertahankan player tetap hidup. |
| Lip-sync | Sudah ada noise gate, normalisasi adaptif, dan exponential smoothing. | Fokus pada attack/release, sinkronisasi, dan reset saat interupsi. |
| Latency | PerfTimer dimulai pada request Hermes, berakhir ketika chunk TTS tersedia. | “Total” belum mencakup endpointing/STT atau waktu audio benar-benar terdengar. |
| Ekspresi avatar | Konfigurasi dicocokkan dengan nama hotkey secara fuzzy. | Mapping belum sesuai aset lokal; audit rinci ada di bagian 8. |

Rujukan: orchestrator.py, hermes_bridge.py, stt_engine.py, tts_engine.py, audio_player.py, audio_analyzer.py, face_tracker.py, vts_connector.py, emotion_parser.py, config.yaml, dan ui/app.js.

## 3. Identitas, perhatian, dan ingatan

| Kemampuan | Pertanyaan yang dijawab |
| --- | --- |
| Face detection | Ada wajah di mana? |
| Face tracking | Apakah wajah ini sama dengan beberapa frame sebelumnya? |
| Face recognition | Apakah wajah cocok dengan profil terdaftar? |
| Speaker diarization | Pembicara mana berbicara pada rentang waktu tertentu? |
| Speaker recognition | Apakah suara cocok dengan profil terdaftar? |
| Active speaker detection | Wajah mana menghasilkan suara yang terdengar? |
| Attention / turn policy | Apakah ucapan ditujukan ke Chassie dan perlu dijawab sekarang? |
| Memory policy | Konteks milik siapa yang boleh dipakai dalam sesi ini? |

Track ID bukan identitas permanen. Label speaker_0 juga tidak otomatis menunjuk orang yang sama pada sesi berikutnya. Mendeteksi wajah baru tidak berarti mengizinkan orang itu bergabung.

### Profil lokal yang direkomendasikan

- Enrollment eksplisit, satu orang berbicara pada satu waktu, dengan sampel jelas. Nama adalah label yang dipilih/dikonfirmasi pengguna.
- Wajah dan suara boleh didaftarkan terpisah. Kamera mati tidak otomatis menghapus identitas yang cukup didukung suara.
- Simpan embedding, versi model, kualitas, dan persetujuan. Rekaman mentah tidak disimpan permanen secara default.
- Hasil boleh unknown atau uncertain; jangan selalu memilih profil terdekat. Threshold harus dikalibrasi dari pengujian, bukan menyalin angka contoh library.
- Jangan memperbarui profil dari overlap atau kecocokan meragukan. Koreksi identitas tidak boleh diam-diam mencampur profil.
- Sediakan hapus profil, cabut persetujuan, dan hapus memori terkait. Batasi akses penyimpanan lokal; embedding tetap data identitas, bukan data anonim.
- Pengenalan wajah/suara membantu personalisasi, bukan satu-satunya otorisasi membuka informasi personal atau melakukan tindakan sensitif.

### Pemisahan memori

| Jenis | Isi dan aturan |
| --- | --- |
| Identitas | Profil terdaftar dan hubungan wajah/suara; bukan seluruh percakapan. |
| Sesi | Giliran aktif, peserta yang diizinkan, ucapan, dan observasi sementara. |
| Personal | Preferensi/fakta dengan sumber, waktu, dan mekanisme koreksi/hapus. Tidak otomatis tersedia bagi tamu. |
| Bersama | Informasi yang memang dibagikan dalam sesi pemilik + tamu. |

Penyaringan konteks dilakukan sebelum request model, bukan hanya melalui instruksi agar model tidak membocorkan riwayat. Kehadiran tamu juga memengaruhi jawaban personal yang sedang disiapkan atau diputar lewat speaker. Mengenali teman tidak sama dengan mengizinkannya mendengar memori personal pemilik.

## 4. Interupsi dan giliran bicara

Contoh: pemilik sedang meminta bantuan debugging, lalu teman masuk dan bertanya kepada pemilik tentang rencana pergi. Chassie mencatat kehadiran tambahan, mempertahankan giliran pemilik yang belum selesai, dan menunggu percakapan samping selesai. Ucapan teman tidak digabung sebagai instruksi pemilik. Pemilik bisa kembali dengan “lanjut tadi”.

Jika teman menyapa Chassie untuk bergabung, statusnya calon peserta sampai pemilik mengizinkan. Setelah itu gunakan konteks bersama. Izin bergabung bukan persetujuan otomatis menyimpan profil wajah/suara.

Dua alur berbeda:

1. **Manusia menyela manusia:** pertahankan kepemilikan giliran, tandai pergantian/overlap, dan jangan gabungkan ucapan menjadi satu instruksi.
2. **Manusia menyela Chassie:** jeda output dengan cepat, evaluasi apakah ucapan mengambil giliran, lalu batalkan atau lanjutkan secara terkendali.

Menjeda output dan menerima instruksi baru merupakan keputusan berbeda. Bukti interupsi bisa cukup untuk jeda sementara sebelum identitas pasti. Tidak setiap “hmm” atau tawa perlu membatalkan jawaban.

Speaker + mic bersama memerlukan penanganan echo dengan referensi audio keluaran Chassie dan sinkronisasi input. webrtcvad yang terpasang belum menyediakan integrasi AEC. Menonaktifkan mic selama TTS menghilangkan barge-in; jika fallback ini diperlukan, tampilkan sebagai mode terbatas yang eksplisit.

Satu mikrofon tidak menjamin ucapan overlap dapat dipulihkan. Diarization memberi label pembicara; source separation merupakan kemampuan tambahan. Jika isi tidak jelas, minta pengulangan alih-alih mengarang atau memaksakan atribusi.

## 5. Matriks skenario

| Kasus | Perilaku yang diharapkan |
| --- | --- |
| Teman lewat di belakang | Tidak menyapa otomatis atau berpindah fokus. |
| Wajah teman lebih besar/dekat | Fokus tidak ditentukan hanya oleh ukuran bounding box. |
| Dua peserta bertukar posisi | Identitas tidak ditentukan posisi kiri/kanan. |
| Pemilik keluar frame sebentar | Pertahankan sesi; tandai wajah tidak terlihat. |
| Pemilik berbicara di luar frame | Jangan mengaitkan ucapan ke satu-satunya wajah yang terlihat. |
| Kamera gelap/tertutup/terputus | Gunakan audio; konteks visual lama kedaluwarsa. |
| Kacamata, masker, sudut wajah berubah | Turunkan keyakinan, jangan langsung membuat profil baru. |
| Wajah/suara mirip | Gunakan uncertain; konfirmasi sebelum memakai konteks personal. |
| Wajah cocok A, suara cocok B | Jangan gabungkan identitas; mungkin ada pembicara di luar kamera. |
| Orang baru mengaku pemilik | Pengakuan tidak otomatis menimpa profil atau memberi akses. |
| Foto/video wajah atau rekaman suara | Jangan menjadi dasar tunggal akses personal; evaluasi spoofing sesuai kebutuhan produk. |
| Teman berbicara kepada pemilik | Tunggu, jangan menjawab percakapan samping. |
| Tamu yang diizinkan menyapa | Jawab memakai konteks bersama dan label peserta yang sesuai. |
| Dua orang berbicara bersamaan | Tandai overlap; minta pengulangan jika tidak jelas. |
| Respons singkat: ya/no/stop | Jangan dibuang hanya karena pendek; identitas boleh belum pasti. |
| Batuk/tawa/menguap | Tidak otomatis menjadi instruksi atau akhir giliran. |
| Pemilik berhenti untuk berpikir | Toleransi jeda dengan batas waktu yang dapat diuji. |
| “Hmm” ketika Chassie bicara | Bedakan respons pendengar dari permintaan mengambil giliran. |
| Suara Chassie masuk mikrofon | Hindari loop membalas diri sendiri. |
| TV/YouTube menyebut Chassie | Nama panggilan saja tidak cukup untuk menerima instruksi. |
| Interupsi ketika Hermes berpikir | Jawaban lama tidak diputar setelah giliran baru. |
| Interupsi ketika TTS diproduksi | Batalkan produksi, tolak chunk lama yang terlambat. |
| Interupsi ternyata suara latar | Lanjutkan terkendali tanpa kehilangan konteks. |
| Tamu masuk saat jawaban personal diputar | Jeda output personal; kehadiran berbeda dari izin bergabung. |
| Pemilik pergi, tamu tetap ada | Jangan melanjutkan konteks personal pemilik. |
| Tamu meminta riwayat pemilik | Riwayat personal tidak masuk request sesi tamu. |
| Riwayat dihapus saat request berjalan | Request lama tidak mengisi ulang riwayat yang dihapus. |
| Mic dimute dengan input tertunda | Hentikan capture dan buang input suara tertunda agar tidak dikirim belakangan. |
| Banyak browser terhubung | Mode suara tidak berubah; cegah submit ganda dan atribusi pemilik tanpa dasar. |
| TTS/internet gagal | Teks tetap tersedia, error jelas, tidak tersangkut speaking. |
| Mic/kamera dicabut atau berubah | Status unavailable, recovery terkendali, tanpa replay input lama. |
| GPU penuh/inference lambat | Prioritaskan capture dan stop; turunkan pekerjaan vision. |
| Screenshot berubah sebelum jawaban | Tandai hasil lama, jangan mengaku melihat kondisi terkini. |
| Layar berisi password/notifikasi pribadi | Batasi aplikasi/area capture; jangan kirim seluruh layar otomatis. |
| Layar berisi instruksi untuk asisten | Perlakukan sebagai data, bukan instruksi sistem. |
| Wajah terdeteksi frowning | Jangan menyimpulkan marah atau kondisi psikologis sebagai fakta. |

## 6. Model vision dan audio: apakah perlu YOLO?

YOLO belum wajib untuk kebutuhan awal. Pilih komponen berdasarkan tugas, bukan satu model untuk seluruh persepsi.

| Kebutuhan | Baseline untuk dievaluasi | Batas |
| --- | --- | --- |
| Landmark/kedipan/kepala | MediaPipe yang sudah ada | Bukan identitas; multiwajah perlu asosiasi track dan smoothing per peserta. |
| Pengenalan wajah lokal | YuNet + SFace melalui OpenCV | Kandidat benchmark, perlu kalibrasi pada perangkat/ruangan target. |
| Pencocokan suara | Speaker embedding/verification, misalnya SpeechBrain | Ucapan singkat, noise, dan overlap mengurangi keyakinan. |
| Rentang pembicara | pyannote sebagai baseline diarization | Pemrosesan rekaman tidak membuktikan latency streaming. |
| Hubungan wajah–suara | Audio-visual active speaker detection seperti TalkNet | Perlu timestamp dan sinkronisasi; mulut terbuka saja tidak cukup. |
| Orang/benda dalam ruangan | YOLO jika kebutuhan ini dipilih | Tracking objek tidak menentukan profil terdaftar atau tujuan ucapan. |
| Pemahaman layar | Metadata aplikasi, OCR, lalu VLM sesuai kebutuhan | Dukungan gambar gateway Hermes belum diverifikasi. |

Mode VIDEO/LIVE_STREAM MediaPipe dapat memakai tracking untuk mengurangi deteksi. Smoothing bawaan Face Landmarker hanya berlaku saat num_faces=1; menaikkan jumlah wajah saja tidak menghasilkan identitas stabil.

Jangan langsung memasang semua model. Tambahkan komponen ketika baseline menunjukkan kegagalan yang jelas. Identitas tetap lokal; izin hybrid tidak otomatis mengizinkan pengiriman raw kamera, biometrik, atau seluruh layar ke cloud.

## 7. Arah kontrak data dan kontrol

Ini kebutuhan antarmuka minimum, belum schema final atau perubahan API yang disetujui.

```text
Mic + referensi playback → AEC/VAD → segmen + STT + pembicara
                                                   ↓
Kamera → track wajah + kandidat profil → peserta + giliran
                                                   ↓
Layar bertimestamp → konteks yang diizinkan → Hermes
                                                   ↓
                          TTS + playback + avatar dapat dibatalkan
```

- Event audio: speech start/end, timestamp, referensi segmen, pembicara sementara, dan ketidakpastian. Kontrol interupsi tidak menunggu transkripsi selesai.
- Observasi wajah: track, kandidat profil, kualitas, waktu. Tidak ada wajah berbeda dari ekspresi neutral.
- Sesi: pemilik giliran, peserta yang diizinkan, dan konteks personal/bersama.
- turn_id/generation_id diteruskan sampai chunk audio dan ekspresi. Hasil terlambat dari giliran batal ditolak.
- Konteks: sumber, peserta terkait, timestamp, masa berlaku. Gunakan waktu monotonic untuk interval dan penyelarasan event lokal.
- Cancellation mencakup request bila didukung, TTS, antrean, buffer playback, dan animasi tertunda. Jika server tidak bisa dibatalkan, klien tetap menolak hasil lama.
- Riwayat membedakan teks dihasilkan, ditampilkan, dan diucapkan. Jawaban terinterupsi tidak dianggap seluruhnya sudah didengar.
- Antrean dibatasi; capture dan kontrol interupsi didahulukan daripada screenshot/inference visual usang.

## 8. Audit ekspresi, FX, outfit, dan parameter model

### 8.1 Ketidakcocokan yang sudah ditemukan

config.yaml memakai smile, cry, shyness, whoa, dan fx_note. VTSConnector._fuzzy_find_hotkey() mencari nama hotkey, bukan file ekspresi. model/ulvm2_0001.vtube.json masih memakai nama seperti 笑顔目（まばたき, ふぇぇ, 照れ, dan fx_♪.

Simulasi pencocokan terhadap inventaris lokal hanya menemukan ekspresi zzz dan FX fx_zzz untuk sleepy. Mapping non-null lainnya tidak cocok. Neutral memang tidak membutuhkan ekspresi/FX. Ini temuan file lokal, bukan verifikasi model yang sedang dimuat di VTS; salinannya dapat berbeda.

Bedakan:

- Tag emosi: maksud semantik Hermes, misalnya happy.
- Nama hotkey: label tampilan VTS yang dapat diganti pengguna.
- ID hotkey: pengenal hotkey pada model VTS tertentu, tidak diasumsikan tetap setelah model diganti.
- File ekspresi: .exp3.json berisi perubahan parameter.
- ID parameter: pengenal rig seperti Param80, ParamMouthOpenY, e2_ParamCheek. Jangan diganti hanya agar mirip nama emosi.

### 8.2 Kandidat mapping seluruh emosi

File kandidat berada di model/animation/. Semua mapping berikut untuk preview, belum persetujuan visual. Emosi berbeda boleh berbagi aset; jangan mengarang kemampuan yang tidak tersedia pada rig.

| Emosi | Konfigurasi sekarang: ekspresi / FX | Kandidat aset: ekspresi / FX | Catatan |
| --- | --- | --- | --- |
| happy | smile / fx_note | smile.exp3.json / fx_3_note.exp3.json | Preview senyum dan kedipan. |
| sad | cry / fx_pale | cry.exp3.json / fx_2_pale2.exp3.json | Uji intensitas untuk sedih ringan. |
| surprised | whoa / fx_surprise | surprised.exp3.json / fx_6_surprised.exp3.json | Alias whoa tidak cocok hotkey lokal. |
| thinking | — / fx_question | — / fx_7_question.exp3.json | Tidak perlu memaksakan ekspresi tambahan. |
| teasing | cat mouth / — | cat_mouth.exp3.json / — | Uji konflik bentuk mulut/lip-sync. |
| concerned | — / fx_sweat_fixed | — / fx_4_sweat.exp3.json | FX fixed sesuai maksud konfigurasi. |
| excited | smile / fx_kirakira | smile.exp3.json / fx_11_star.exp3.json | Bedakan dari happy melalui FX/intensitas. |
| neutral | — / — | Nonaktifkan ekspresi/FX milik Chassie | Outfit tidak direset. |
| angry | xx_eyes / fx_anger | angry.exp3.json / fx_13_angry.exp3.json | Intent lama mengarah mata XD; bandingkan angry/angry2/XD, jangan anggap setara. |
| shy | shyness / — | blush.exp3.json / — | Alias untuk aset blush tersedia. |
| sleepy | zzz / fx_zzz | sleep.exp3.json / fx_12_zzz.exp3.json | Mapping cocok; uji mata/breathing. |
| love | smile / fx_heart | smile.exp3.json / fx_1_heart.exp3.json | Uji transisi happy/excited. |
| defeated | kukkoro / fx_pale | kukkoro.exp3.json / fx_2_pale2.exp3.json | Banyak parameter berubah; perlu preview. |
| curious | jite / fx_question | jitome.exp3.json / fx_7_question.exp3.json | Jitome mungkin terlihat skeptis, bukan penasaran. |
| flustered | oo_eyes / fx_sweat_fixed | oo.exp3.json / fx_4_sweat.exp3.json | Uji perpindahan bentuk mata. |
| shocked | whoa / fx_exclamation | surprised.exp3.json / fx_8_exclamation.exp3.json | Bedakan dari surprised melalui FX. |

### 8.3 Temuan aset untuk runtime

- .model3.json mereferensikan .moc3, lima tekstur, physics, dan display info, tetapi belum mempunyai daftar Expressions atau Motions pada FileReferences.
- Grup EyeBlink dan LipSync ada tetapi ID kosong. Loader standar tidak dapat mengandalkan grup ini untuk binding otomatis tanpa pengaturan tambahan.
- Mapping VTS menghubungkan input MouthOpen ke parameter model ParamMouthOpenY. Runtime Cubism langsung perlu ID parameter model, bukan menyalin ID input VTS.
- costume_v0100.exp3.json memiliki Parameters kosong. Jangan ditawarkan sebagai outfit fungsional sebelum diperiksa. Tiga hotkey outfit lokal mengarah ke v0000, v0052, v0101.
- Nilai parameter sleep.exp3.json berupa string numerik, sementara aset lain umumnya angka. Catat kompatibilitas parser; jangan normalisasi aset tanpa validasi terpisah.
- Banyak ekspresi memakai Blend: Add dan sebagian menulis parameter yang sama. Penggabungan perlu aturan agar tidak saling bertabrakan.
- .vtube.json berisi pengaturan khusus VTS; Cubism tidak otomatis menerapkan hotkey, smoothing, dan seluruh mapping di dalamnya.

### 8.4 Rekomendasi pengelolaan

1. Gunakan mapping eksplisit per model dengan referensi aset, bukan fuzzy matching label. Query inventaris model yang aktif di VTS sebelum menyatakan valid.
2. Evaluasi ExpressionStateRequest dan ExpressionActivationRequest untuk membaca status serta menetapkan aktif/nonaktif berdasarkan file. Sediakan reset manual agar pengguna dapat memulihkan ekspresi saat plugin bermasalah.
3. Pisahkan state ekspresi, FX, dan outfit. Neutral/reset emosi tidak mematikan outfit. Jangan memakai RemoveAllExpressions tanpa memahami dampaknya.
4. Atur sumber kendali: mulut ketika Chassie bicara dari TTS, ekspresi dari karakter, blink/head movement dari controller. Meniru wajah pemilik adalah mode tersendiri.
5. Serialisasikan atau gabungkan transisi usang. Tugas async tidak boleh saling toggle atau memutar ekspresi generasi batal.
6. Rekonsiliasi setelah reconnect, perubahan model, dan hotkey manual. State lokal tidak selalu sama dengan VTS.
7. Preview ekspresi satu per satu dan kombinasi penting. Renaming hotkey boleh menjadi opsi kenyamanan, tetapi bukan fondasi integrasi.

## 9. Runtime mandiri dibanding VTS

Runtime mandiri bisa lebih sesuai untuk Chassie, tetapi tidak otomatis lebih bagus secara visual, lebih ringan, atau lebih stabil. Dengan .moc3 dan tekstur yang sama, deformasi dasar mengikuti rig yang sama. Fitur yang membutuhkan rig tambahan tidak muncul hanya karena mengganti renderer.

| Aspek | Target / peluang | Biaya atau batas |
| --- | --- | --- |
| Rendering | Mendekati tampilan VTS dengan aset yang sama | Masking, alpha, draw order, scaling, dan warna harus benar. |
| Physics | Memakai physics model yang tersedia | Timing dan pengaturan dapat menghasilkan gerakan berbeda. |
| Lip-sync/ekspresi | Satu timeline dengan audio dan cancellation | Tetap perlu blending, prioritas parameter, dan pengujian. |
| Perilaku karakter | Idle, mendengarkan, berpikir, perhatian ke peserta | Sebagian juga bisa dibangun di atas VTS; bukan alasan tunggal migrasi. |
| Desktop | UX/startup khusus Chassie | Transparansi, click-through, drag, DPI, multi-monitor, fokus, dan recovery harus dibangun. |
| Performa | Potensi mengurangi pekerjaan yang tidak digunakan | Benchmark CPU/GPU/RAM/VRAM; wrapper web atau aset besar dapat tetap berat. |
| Fitur aplikasi | Ambil fitur VTS yang memang digunakan | Tracking, hotkey UI, item, efek, dan konfigurasi tidak otomatis ikut pindah. |
| Pemeliharaan | Kendali penuh perilaku aplikasi | Kompatibilitas SDK, perangkat, packaging, dan recovery menjadi tanggung jawab aplikasi. |

Tahap yang direkomendasikan:

1. Stabilkan mapping dan perilaku VTS sebagai baseline.
2. Buat AvatarController dengan backend VTS. Kontrak tidak bergantung nama hotkey: ekspresi/FX, outfit, parameter terpetakan, reset milik Chassie, cancellation event lama.
3. Spike runtime mandiri dengan model yang sama: render, physics, mata, lip-sync, ekspresi, outfit. Manifest dan binding parameter dibuat eksplisit.
4. Bandingkan visual/performa pada input serta resolusi yang sama. Jangan mengklaim parity seluruh VTS jika hanya subset yang diuji.
5. Tambahkan perilaku karakter setelah baseline stabil; VTS tetap fallback.

Belum diputuskan: native/Web/Unity atau wrapper lain, OS target, detail interaksi overlay, anggaran resource. Pemilihan SDK/distribusi model perlu memeriksa ketentuan aset yang dipilih; keberadaan file lokal tidak membuktikan hak distribusinya.

### 9.1 Overlay desktop tanpa background

Target yang disetujui: avatar tampak mengambang di kanan bawah layar dengan area di luar model transparan, tanpa panel persegi atau background gambar. Transparansi tampilan dan kemampuan klik menembus jendela adalah dua fitur berbeda.

Default yang diusulkan untuk dibahas:

- Overlay berada di atas jendela aplikasi biasa, tanpa mengambil fokus keyboard ketika pengguna sedang bekerja.
- Posisi awal kanan bawah pada area kerja monitor, dengan jarak dari taskbar/dock agar model tidak terpotong. Posisi dan ukuran dapat disesuaikan serta diingat.
- Mode normal click-through agar klik tetap sampai ke aplikasi di belakang. Mode pengaturan diaktifkan lewat kontrol terpisah untuk drag/resize; akses kontrol harus tetap tersedia saat click-through aktif.
- Kontrol cepat untuk sembunyikan/tampilkan, mute mikrofon, dan menghentikan suara. Menyembunyikan avatar tidak disamakan dengan mute; statusnya jelas.
- Model dan FX tetap berada dalam batas overlay, termasuk ketika ekspresi, physics, atau outfit berubah.
- Saat monitor dilepas atau skala DPI berubah, posisi dipulihkan ke area layar yang terlihat.

Dukungan always-on-top, posisi, transparansi, dan click-through perlu divalidasi pada OS/window system target. Overlay pada game fullscreen eksklusif belum dijanjikan. Target visual ini tidak otomatis menentukan pilihan runtime.

## 10. Audio, TTS, dan screen perception

### TTS/latency

- Pertahankan Edge TTS Inggris; tidak ada pekerjaan mengganti voice ke Indonesia.
- In-memory perlu decoding MP3 yang benar. Mengumpulkan semua byte ke RAM menghapus I/O file tetapi belum streaming PCM.
- Pisahkan token streaming Hermes, sentence chunking, decoding audio bertahap, dan prebuffer.
- Verifikasi kontrak gateway sebelum merancang streaming Hermes; kemiripan format API belum membuktikan dukungan.
- Pertahankan makna emotion parser saat chunking; uji tag terpotong, singkatan, desimal, dan code block.
- Sertakan antrean terbatas, timeout, cancellation, serta error audio kosong.
- Voice alternatif masih terbuka; kualitas tidak diklaim tanpa uji dengar.

### Screen perception

- Mulai dari metadata aplikasi/window melalui adapter OS. FaceTracker bukan implementasi screen perception.
- Capture eksplisit dengan batas aplikasi/area, status yang terlihat, dan kontrol penghentian.
- Change detection disertai rate limit, timestamp, dan pembuangan hasil usang.
- Pakai OCR/VLM bila perlu. Ringkasan tidak menjamin screenshot aman; pembatasan diterapkan sebelum pengiriman.
- Konten layar adalah data tidak tepercaya; tidak boleh mengubah instruksi sistem atau memberi otorisasi tindakan.

## 11. Roadmap berdasarkan dependensi

Urutan lama 001 → 002 → ... → 015 tidak lagi wajib. Identitas, aturan konteks, dan pembatalan dibutuhkan lebih awal untuk personal + tamu.

| Prioritas | Hasil |
| --- | --- |
| P0 — Baseline/audit aset | Mute nyata, input konsisten, capture tidak terblokir transkripsi, metrik end-to-end, mapping ekspresi dapat diperiksa. |
| P1 — Interupsi | Echo handling, speech events, cancellation lintas pipeline, endpointing, antrean terbatas. Mulai dari pemilik tunggal. |
| P2 — Personal + tamu | Track peserta, profil opt-in, unknown/uncertain, izin bergabung, pemisahan memori/konteks. Jangan aktifkan tamu sebelum batas konteks tersedia. |
| P3 — Kualitas respons | Streaming jika gateway mendukung, chunking, transport TTS, prebuffer, sinkronisasi ekspresi. Perbaikan independen boleh lebih awal berdasarkan pengukuran. |
| P4 — Layar | Metadata, capture terkontrol, freshness, OCR/VLM sesuai kebutuhan. |
| P5 — Runtime | Abstraksi backend sebelum runtime baru, kesetaraan subset VTS, lalu perilaku tambahan. Pose opsional. |

### Pemetaan PRD lama

Nomor berikut berasal dari evaluasi sebelumnya, bukan bukti file PRD terpisah sudah tersedia.

| PRD | Topik | Penyesuaian |
| --- | --- | --- |
| 001 | TTS in-memory | Koreksi format MP3; pisahkan transport dari streaming. |
| 002 | Sentence chunking | Tidak menghilangkan waktu generasi Hermes tanpa streaming. |
| 003 | Prebuffer | Manfaatkan thread/queue; tambah batas dan cancellation. |
| 004 | Barge-in | AEC, speech start, pembatalan buffer/produsen, kebijakan giliran. |
| 005 | Adaptive speech end | Jeda berpikir, overlap, respons singkat, batas durasi. |
| 006 | Lip-sync smoothing | Sudah ada; fokus tuning, sinkronisasi, reset. |
| 007 | Active window | Bergantung OS; belum diimplementasikan. |
| 008 | Screen capture/change | Izin capture, freshness, rate limit. |
| 009 | Vision context | Verifikasi model/gateway, batas data, hasil usang. |
| 010 | Avatar runtime | Setelah kontrak controller dan audit aset. |
| 011 | Expression abstraction | Dahulukan sebelum runtime; mapping eksplisit, rekonsiliasi state. |
| 012 | Outfit | Pisahkan dari emosi; jangan aktifkan aset kosong. |
| 013 | Face → avatar | Pisahkan persepsi pengguna dari mode meniru wajah. |
| 014 | Pose | Opsional setelah kebutuhan produk/baseline stabil. |
| 015 | Context-aware | Fondasi konteks/giliran lebih awal; pengayaan multimodal kemudian. |

Kandidat topik baru, belum PRD final: event audio/cancellation, echo handling, identitas peserta, enrollment, izin tamu, pemisahan memori, audit model/manifest, observability/recovery.

## 12. Pengujian dan penerimaan

### Kumpulan uji

Rekaman berizin: pemilik sendiri, pemilik + tamu, overlap, suara Chassie dari speaker, TV latar, cahaya rendah, perubahan posisi, keluar-masuk frame, perangkat putus. Tambahkan bahasa campuran bila input tersebut dipilih. Pisahkan sampel enrollment dari rekaman evaluasi.

### Metrik

- Mulai menyela sampai audio benar-benar berhenti; p50/p95, bukan hanya rata-rata.
- Akhir ucapan sampai audio jawaban pertama terdengar: endpointing, STT, Hermes, TTS, dan buffer perangkat.
- Salah interupsi karena echo/TV/batuk, serta interupsi pemilik terlewat.
- Salah mengenali, gagal mengenali, uncertain/unknown, dan salah atribusi ucapan.
- Audio hilang/overflow, panjang antrean, tugas usang, CPU/GPU/RAM/VRAM, stabilitas sesi panjang.
- Frame time dan selisih audio–mulut/ekspresi pada resolusi sama untuk VTS dan runtime.

Target angka belum ditetapkan. Ukur baseline perangkat sebelum menjanjikan latency/akurasi.

### Acceptance scenario wajib

- Mute menghentikan capture; input suara tertunda tidak dikirim belakangan.
- Tidak ada audio, respons, atau ekspresi generasi batal pada giliran baru.
- Capture tetap berjalan ketika STT/vision lambat; resource/antrean terbatas.
- Observasi kedaluwarsa tidak dipakai sebagai keadaan terkini.
- Konteks personal tidak masuk request tamu pada skenario uji, termasuk tamu masuk di tengah generasi/playback.
- Semua 16 emosi punya mapping terverifikasi atau fallback eksplisit; neutral bukan mapping gagal.
- Emosi berulang tidak men-toggle menjadi mati. Pergantian cepat, reset, interupsi, reconnect, dan hotkey manual tidak meninggalkan state tertinggal.
- Ekspresi/FX tidak mengubah outfit. Aset hilang/kosong menghasilkan status jelas.
- Runtime diuji dengan manifest, physics, blink, lip-sync, dan urutan ekspresi yang sama dengan VTS; belum ada klaim parity sebelum perbandingan visual.
- Kegagalan layanan/perangkat tidak membuat UI tersangkut atau memutar ulang output lama saat pulih.
- Overlay memiliki alpha transparan tanpa kotak background; tepi model/FX tidak terpotong. Uji posisi kanan bawah, taskbar/dock, resize, DPI, dan perubahan monitor.
- Jika default interaksi overlay diterima, uji click-through, masuk/keluar mode pengaturan, serta akses hide/mute/stop tanpa mencuri fokus aplikasi aktif.

Lulus kumpulan uji merupakan bukti pada skenario yang diuji, bukan jaminan tidak pernah salah.

## 13. Pertanyaan diskusi terbuka

1. OS deployment akhir dan penggunaan bersamaan dengan game/aplikasi berat. Kapasitas sudah dikonfirmasi: VRAM 4 GB, RAM 8 GB.
2. Akurasi Indonesia + Inggris dan pergantian bahasa dalam satu ucapan; pilihan bahasanya sudah dikonfirmasi.
3. Cara pemilik mengundang tamu/mengonfirmasi identitas: UI, suara, atau keduanya.
4. Kapan jawaban dijeda dilanjutkan otomatis atau menunggu pemilik menyapa.
5. Retensi memori, penghapusan, serta informasi yang boleh dipakai cloud.
6. Mapping angry/curious dan intensitas FX setelah preview.
7. Overlay transparan kanan bawah sudah dipilih; konfirmasi detail click-through, drag/resize, kontrol, dan apakah dukungan gaming menjadi kebutuhan awal.
8. Penggunaan utama (kerja/santai/gaming) dan seberapa aktif Chassie boleh memulai percakapan. Default fokus masih rekomendasi.

## 14. Referensi teknis

Diperiksa dalam sesi evaluasi. Kandidat library/model bukan keputusan final atau hasil benchmark lokal.

- [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/python): mode streaming, landmark/blendshape, batas smoothing multiwajah.
- [OpenCV YuNet/SFace](https://docs.opencv.org/4.13.0/d0/dd4/tutorial_dnn_face.html): deteksi/pencocokan wajah.
- [SpeechBrain SpeakerRecognition](https://speechbrain.readthedocs.io/en/latest/API/speechbrain.inference.speaker.html): speaker verification.
- [pyannote Community-1](https://huggingface.co/pyannote/speaker-diarization-community-1): diarization lokal; bukan bukti latency streaming.
- [TalkNet](https://github.com/TaoRuijie/TalkNet-ASD): active speaker detection audio-visual.
- [Ultralytics tracking](https://docs.ultralytics.com/modes/track): tracking objek berbeda dari identitas/kebijakan percakapan.
- [WebRTC APM](https://webrtc.googlesource.com/src/%2B/f981cb3d2e2b053669c2827332574907128592f3/modules/audio_processing/g3doc/audio_processing_module.md): echo cancellation/pemrosesan audio.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): konfigurasi model/transkripsi.
- [edge-tts](https://github.com/rany2/edge-tts) dan [format MP3](https://github.com/rany2/edge-tts/discussions/166): TTS online/format keluaran, bukan rekomendasi voice Indonesia.
- [VTube Studio API](https://github.com/DenchiSoft/VTubeStudio#requesting-current-expression-state-list): status/inventaris, aktivasi file ekspresi, hotkey.
- [Ekspresi Cubism](https://docs.live2d.com/en/cubism-sdk-manual/expression/): ekspresi/blending.
- [Lip-sync Cubism](https://docs.live2d.com/cubism-sdk-manual/lipsync/): binding dan kendali parameter mulut.
