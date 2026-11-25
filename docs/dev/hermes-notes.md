# Hermes API untuk Chassie

Pemeriksaan lokal 8 September 2026 menemukan Hermes berjalan sebagai **systemd user service** `hermes-gateway.service`, semula PID 828. Layanan aktif sejak 10:03 WIB dan otomatis bertahan ketika terminal ditutup. Menjalankan `hermes gateway` lagi menolak instance kedua; itu tidak berarti API HTTP sudah aktif.

```bash
systemctl --user status hermes-gateway.service --no-pager --lines=0
```

Pada pemeriksaan awal, tidak ada listener port 8642, dan konfigurasi tidak memiliki `API_SERVER_KEY`. Source Hermes yang terpasang (`gateway/platforms/api_server.py`, `_api_key_passes_startup_guard`) mewajibkan key kuat minimal 16 karakter, termasuk untuk localhost. Catatan lama “gateway tidak perlu key” sudah tidak berlaku untuk versi ini.

## Konfigurasi yang disiapkan

Chassie membaca key dari environment `CHASSIE_HERMES_API_KEY`, lalu `hermes.api_key` bila diberikan, lalu file lokal `.chassie/hermes-api-key`. File tersebut diabaikan source control dan harus hanya dapat dibaca pengguna pemilik. Key tidak dikirim ke browser dan tidak perlu ditempel ke chat.

Pengaktifan sisi Hermes membutuhkan pengaturan berikut di `~/.hermes/.env`:

```dotenv
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
# API_SERVER_KEY berisi secret acak kuat, misalnya 32 byte; bukan placeholder.
```

Key yang sama disimpan di file privat Chassie. Setelah membuat backup `.env`, restart instance yang ada:

```bash
systemctl --user restart hermes-gateway.service
```

**Status:** pengguna menyetujui pengaktifan dan restart; keduanya selesai pada 8 September 2026. Backup konfigurasi tersimpan sebagai `~/.hermes/.env.before-chassie-20260908-122055`. `.env` dan file key Chassie berizin `0600`. Layanan kembali `active/running`, PID 43825 pada pemeriksaan, dengan listener hanya di `127.0.0.1:8642`.

Verifikasi: `/health` dengan autentikasi berhasil; `/v1/models` tanpa key ditolak HTTP 401. Chassie tetap diarahkan ke `http://localhost:8642`, endpoint `/v1/chat/completions`.

Tes awal mencapai gateway, tetapi `deepseek-v4-flash-free` mengembalikan **HTTP 429 karena kuota gratis bersama habis**. Gateway membungkus kegagalan tersebut sebagai teks assistant dalam HTTP 200. Client kini mengenali format kegagalan ini dan menampilkan notice tanpa memasukkannya ke riwayat atau TTS.

**Tes ulang awal setelah pengguna mengganti model ke `Combo_AI`:** health berautentikasi tetap berhasil. Permintaan pertama melalui HermesBridge menghasilkan kegagalan provider; satu percobaan ulang langsung ke endpoint chat melewati timeout client 30 detik. Ini belum membuktikan penyebab kegagalan provider yang baru sama dengan kuota model sebelumnya. Bukti percobaan awal tersanitasi berada di `.test-artifacts/hermes-live-check.json`.


## Diagnosis waktu tunggu, 8 September 2026

Percobaan sintetis langsung ke endpoint SSE pada sekitar 13:56 WIB kemudian berhasil: HTTP 200 dalam 0,007 detik, chunk role tanpa teks dalam 0,008 detik, teks pertama (22 karakter) dalam 22,839 detik, dan `stop` + `[DONE]` dalam 22,854 detik. Tidak ada event penggunaan tool. Tes ini melewati STT, TTS, dan pemutaran audio; bukan pengukuran waktu sampai suara terdengar atau perbandingan sebelum/sesudah optimasi.

Log Hermes untuk sesi `api-2621601bb8ac6ea6` mencatat satu panggilan model `Combo_AI` selama 7,0 detik, dengan 15.795 input token dan nol tool turn. Sekitar 15,8 detik mendahului panggilan model. Pada rentang persiapan tersebut terdapat dua kegagalan deteksi context length untuk endpoint lokal port 20128, lalu fallback ke 256.000 token. Angka 15,8 detik mencakup seluruh persiapan, bukan pengukuran terisolasi durasi probe saja.

Source Hermes terpasang menunjukkan `_run_agent` membuat agent baru setiap permintaan API. `agent/model_metadata.py` memakai probe HTTP sinkron dengan timeout dan hanya menyimpan hasil probe positif; hasil gagal dapat diprobe lagi. Pengaturan eksplisit context length diperiksa sebelum probe. Ini menjelaskan sumber overhead yang teramati; perbandingan terkontrol dengan sesi CLI yang sudah aktif belum dilakukan. Pengguna memakai round-robin, sehingga backend sebenarnya dan latensinya juga dapat berbeda antarpermintaan.

Tindak lanjut: tentukan batas konteks yang didukung seluruh anggota round-robin, lalu atur override khusus alias/provider tersebut dan ulangi pengukuran. Jangan menyalin fallback 256.000 sebagai kapasitas yang sudah terbukti. Konfigurasi Hermes belum diubah dalam diagnosis ini. Prompt inti/tools Hermes juga menambah input bahkan untuk pertanyaan singkat; dampak pengurangannya belum diukur.

### Tes ulang setelah pengguna mengubah routing menjadi fallback

Pada 14:09 WIB, prompt sintetis yang sama berhasil menghasilkan tepat `Connection successful.` dan selesai dengan `stop` + `[DONE]`. Header/role SSE diterima pada 0,016 detik, teks pertama 34,248 detik, selesai 34,281 detik. Alias model pada konfigurasi dan log sekarang `hermes`; `model.context_length` masih kosong. Dua kegagalan deteksi context length kembali tercatat. Panggilan model memakan 19,5 detik (17.877 input token, nol tool turn), sehingga sisa waktu sebelum/di luar panggilan model sekitar 14,8 detik.

Dalam satu sampel ini teks pertama lebih lambat daripada 22,839 detik sebelumnya. Routing fallback dilaporkan pengguna; konfigurasi internal router dan model upstream yang terpilih belum diverifikasi. Prompt inti/input token juga berbeda, sehingga hasil ini tidak membuktikan fallback secara umum lebih lambat. Overhead persiapan tetap terlihat dan perlu ditangani terpisah dari pemilihan rute. Bukti tersanitasi: `.test-artifacts/hermes-fallback-latency.json`. Tidak ada TTS, rekaman, atau pemutaran suara pada tes ini.

## Perbaikan konfigurasi latensi yang diterapkan

Setelah pengguna mengizinkan perubahan di `~/.hermes`, pemeriksaan router lokal menemukan alias `hermes` berisi satu anggota: `gemini/gemini-3.8-flash`. Katalog lokal router mencatat konteks 1.048.576 token. Pada 8 September 2026 diterapkan batas kerja konservatif **131.072 token**, bukan klaim kapasitas maksimum:

- `model.context_length: 131072` untuk resolver model default dan persiapan tool search.
- `custom_providers` → provider `9router` → `models.hermes.context_length: 131072` untuk lookup alias yang dibatasi endpoint/model.

Kedua jalur diperlukan pada versi Hermes terpasang: tool search tidak meneruskan daftar custom provider ke resolver metadata. Percobaan dengan metadata alias saja masih memicu satu probe. Dengan kedua nilai tersebut, probe gagal tidak muncul lagi dalam request yang diukur. Source Hermes, routing, kredensial, tools, memori, dan reasoning global tidak diubah. Gateway aktif membaca ulang konfigurasi tanpa perlu restart.

Backup lengkap sebelum perubahan: `~/.hermes/config.yaml.before-chassie-latency-20260908-143654` (izin 0600). Backup antara kedua tahap: `~/.hermes/config.yaml.before-chassie-latency-20260908-143951`. Pemeriksaan struktur YAML membuktikan hanya dua nilai konteks di atas yang berubah. Untuk rollback, pulihkan kedua nilai dari backup pertama; jangan menimpa seluruh config apabila ada perubahan pengguna sesudahnya. Evaluasi ulang batas kerja ini bila anggota alias/model diganti.

Chassie kini mengirim `model_options.reasoning_effort: low` pada request sendiri, dikendalikan `hermes.reasoning_effort` di `config.yaml` Chassie. `null` mewarisi Hermes dan `medium` memberi penalaran lebih mendalam untuk pertanyaan rumit. Pengaturan CLI/global tetap `medium`. Restart backend Chassie diperlukan untuk membaca opsi lokal baru ini.

Verifikasi memakai loader asli gateway dan CLI dengan `HERMES_HOME` sementara: resolusi alias/default/tool search berhasil tanpa koneksi jaringan, dan batas alias tidak berlaku untuk endpoint/model lain. Dua tes request gagal sebelum penambahan opsi reasoning; setelah implementasi seluruh **143 tes Chassie lulus dalam 7,20 detik**, termasuk browser dan pembatalan stream. Source Hermes tidak berubah sehingga tidak ada suite perubahan source Hermes yang dijalankan.

Pengukuran sintetis melalui WebSocket Chassie → Hermes nyata → TTS Inggris nyata, dengan memori sementara dan output perangkat palsu:

| Konfigurasi | Teks pertama | PCM pertama |
| --- | ---: | ---: |
| Baseline baru sebelum perubahan | 22,677 dtk | 23,452 dtk |
| Batas konteks lengkap, reasoning medium | 12,825 dtk | 13,431 dtk |
| Eksperimen request low | 6,334 dtk | 7,188 dtk |
| Verifikasi akhir config Chassie low | 19,889 dtk | 21,363 dtk |

Persiapan dari pembuatan client agent sampai awal turn turun menjadi sekitar 0,12–0,13 detik pada dua request terakhir setelah cache hangat (sampel pertama setelah konfigurasi sekitar 2,1 detik). Sisa waktu model tetap bervariasi: log verifikasi akhir mencatat **19,5 detik di panggilan model**, tanpa probe konteks gagal. Jadi perbaikan menghilangkan overhead yang terbukti, tetapi belum membuktikan respons stabil 1–2 detik atau bahwa low selalu lebih cepat. Belum ada perbandingan CLI interaktif dengan request identik. Artefak tersanitasi berada di `.test-artifacts/hermes-context-before.json`, `hermes-context-after.json`, `hermes-reasoning-low-experiment.json`, dan `web-turn-live-check.json`; tidak ada pemutaran suara atau rekaman pengguna.

## Batas pemisahan konteks

Catatan timeout web: interval keepalive Hermes yang terpasang adalah 30 detik, sedangkan Chassie semula memakai batas tanpa data yang sama. Kondisi ini dapat memutus stream sebelum keepalive tiba meskipun agent masih bekerja. Log sekitar 14:19:35–14:20:05 juga mencatat koneksi SSE putus dan agent diinterupsi setelah sekitar 30 detik. Chassie kini menunggu hingga 75 detik tanpa data, dengan batas total tetap 180 detik. Pesan timeout tampil di percakapan dan membedakan batas tanpa data/total. Restart backend Chassie dan reload browser untuk menerapkan perbaikan; konfigurasi Hermes tidak perlu diubah untuk perbaikan timeout ini.

Pipeline percakapan Chassie sekarang mengirim `stream: true` dan memerlukan SSE chat completions. Metode nonstreaming tetap tersedia untuk pemeriksaan/kompatibilitas, tetapi tidak dipakai untuk jalur percakapan utama. Percobaan streaming awal gagal di provider; percobaan diagnosis terbaru di atas selesai bersih. [Verifikasi streaming](superpowers/plans/2026-09-08-streaming-replies.md) mencatat bukti lokal dan batas latency.

API Hermes menambahkan system prompt permintaan di atas konteks inti agennya. Chassie membersihkan riwayat dan memori **milik Chassie** ketika peserta berubah. Ini belum membatasi SOUL, memori global, tools, atau data lain yang disediakan Hermes. Gunakan konfigurasi/profil backend yang sesuai dan uji kebocoran lintas sesi sebelum mengaktifkan penggunaan tamu tanpa pendampingan. Tidak ada pesan ke kontak/platform lain yang digunakan sebagai tes integrasi.
