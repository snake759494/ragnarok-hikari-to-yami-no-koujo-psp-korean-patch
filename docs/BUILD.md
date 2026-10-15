# 빌드 방법

번역 대본·원문은 저장소에 없으므로, 아래는 자신이 가진 원본과 번역 파일로 다시 빌드하는 절차입니다.

## 준비물
- 원본 ISO `Ragnarok - Hikari to Yami no Koujo (Japan).iso` (MD5 `fa0f7c65c5190f5ed2dad6594a3bd974`)
- Python 3.12+ : `pip install pillow numpy opencv-python imageio-ffmpeg websocket-client pycdlib`
- EBOOT 복호화 도구(예: eboot_decrypt), 글꼴 `NanumSquareNeo-*.ttf`, `SeoulHangang*.ttf`

## 폴더 구성
```
<작업 폴더>/
  Ragnarok - Hikari to Yami no Koujo (Japan).iso
  NanumSquareNeo-*.ttf, SeoulHangang*.ttf
  tools/            (이 저장소의 tools)
  translation/      s*.json, e*.json, eboot_utf8.json, tex/*.json  (번역 — 저장소 미포함)
  work/
```

## 순서
1. ISO 추출: pycdlib 등으로 원본 ISO를 `work/iso/` 에 풉니다(파일 구조 그대로).
2. EBOOT 복호화: `eboot_decrypt work/iso/PSP_GAME/SYSDIR/EBOOT.BIN work/eboot_dec.elf`
3. 문자열 추출: `work/cfi/` 에 CFI를 풀고(`tools/cfi.py` 의 `load`/`unz`), `python tools/eboot_extract.py`, `python tools/make_batches.py` → `work/batches/`
4. 번역 작성: `translation/<배치>.json` = `{id: 한국어}`. 검사: `python -I tools/check_batch.py s00 …`
5. 그림 글자: `python tools/dump_textures.py` 로 PNG 추출, `translation/tex/*.json` 사양 작성, `python tools/tex_patch.py preview <사양>` 으로 확인. 라벨 자동 생성: `python tools/gen_label_specs.py`
6. 동영상: `python tools/movie_op1.py` → `work/movie/op1.pmf`
7. 빌드: `python tools/build.py` → `Ragnarok - Hikari to Yami no Koujo (Korean).iso`
8. 남은 일본어 검사: `python tools/scan_untranslated.py`
9. 차분: `xdelta3 -e -0 -s 원본.iso 한글.iso 패치.xdelta`

PPSSPP 원격 디버거로 자동 확인할 때는 `python tools/emu.py start <ISO>` / `shot` / `press` 를 씁니다.
