# arXiv submission — NEXT STEPS (retomar 2026-06-07+)

> Estado al cerrar 2026-06-06: paquete montado, compilado y verificado idéntico al enviado.
> Falta solo decidir metadatos y subir. Lo técnico está hecho.

## ✅ HECHO (verificado)
- Contenido idéntico al enviado: `diff` del `.tex` = solo 7 líneas (venue→Preprint + nota a pie).
- Canónico `paper/SIGSPATIAL_2026/...tex` == commit `050a6d0 "Submitted version"` (git diff vacío).
- PDF compilado vs PDF enviado: diff de palabras (ordenado) explica TODO con 2 cambios; 9 footers "SIGSPATIAL"→9 "Preprint". Cero cambios en cuerpo/números/tablas/citas.
- Paquete: `paper/arxiv/arxiv_geonatureagent.tar.gz` (~202 KB). Compila en aislamiento → 10 páginas, sin errores.
  - Contiene: `geonatureagent_benchmark.tex` (rutas figuras corregidas `../figures/`→`figures/`), `.bbl` precompilado, `acmart.cls`, `ACM-Reference-Format.bst`, `references.bib`, `figures/` (8 PDFs).
- Carpeta de trabajo del build: `paper/arxiv/arxiv_upload/`.

## ⏳ BLOQUEANTE ACTUAL (2026-06-08): endorsement de cs.AI
- arXiv exige endorsement para cs.AI (cuenta de Gabriel: primer envío, email comercial → no auto-endorsed; ni siquiera con jhu.edu).
- **Código de endorsement: `ZKO6IU`** (enlace limpio: https://arxiv.org/auth/endorse?x=ZKO6IU ; fallback: arxiv.org/auth/endorse.php + código).
- **Solicitado a Devika Jain** (kakkar@fas.harvard.edu) el 2026-06-08 — email enviado. ⏳ esperando respuesta.
- Devika CUALIFICA: publica en arXiv como "Devika Jain" (0 papers como "Kakkar"); tiene ≥3 papers cs.* en ventana (2508.06435 cs.CL+**cs.AI**, 2511.03915 cs.CL/cs.CY, 2601.20880 cs.LG); co-autora con Stefano Iacus (Harvard CGA) → identidad confirmada.
- Una vez que ella endose → desbloquea subir. Todo lo demás está listo.
- Fallback si Devika no puede: profesor de CS/AI en JHU (sugerencia de la propia arXiv para grad students), o el Long Yuan de bases de datos (cs.DB cualifica) — pero verificar identidad antes con el link "Which of the authors can endorse?".

## ⬜ POR REVISAR / DECIDIR antes de subir

### 1. ✅ RESUELTO (2026-06-07): CFP permite arXiv sin problema
- SIGSPATIAL 2026 = **single-blind** (nombres/afiliaciones visibles en el envío) → no hay anonimato que romper.
- CFP no tiene cláusula anti-preprint.
- Política oficial ACM: posting a arXiv NO es prior/current publication; "no ACM sponsored conference may reject submissions as a result of ACM authors posting their work to arXiv". Única prohibición = envío simultáneo a otra pub. peer-reviewed (arXiv no lo es).
- Fuentes: sigspatial2026.sigspatial.org/research-submission.html ; acm.org/publications/policies/simultaneous-submissions
- CONCLUSIÓN: luz verde para subir a arXiv.

### 2. Metadatos arXiv (decisión conjunta con Diego)
- **Categoría**: propuesta `cs.AI` (primaria) + cross-list `cs.LG` y/o `cs.CL`. ¿Geo? no hay cat. específica.
- **Licencia**: CC BY 4.0 (coherente con plan Zenodo) vs arXiv non-exclusive. DECIDIR.
- **Comments**: neutro, p.ej. "Preprint. 10 pages, 8 figures." → cambiar a "Accepted at ACM SIGSPATIAL 2026" si entra.
- **Venue en comments**: acordado dejarlo neutro de momento (no afirmar aceptación).

### 3. Autores / afiliaciones / ORCID en el formulario arXiv
- Verificar orden de autores y afiliaciones coincide con el paper.
- Email Gabriel = `gdiazir1@jh.edu` (único correcto).
- Devika surname = **Jain** (confirmado), email `kakkar@fas.harvard.edu`.
- ¿ORCIDs disponibles para meter en arXiv?

### 4. Tag de git de la versión enviada (pendiente, Gabriel lo pidió)
- Sugerido: `git tag -a submitted-sigspatial-2026 050a6d0 -m "Version submitted to SIGSPATIAL 2026"` y `git push --tags`.
- Así la versión arXiv queda anclada a un commit citable.

### 5. Comprobación final pre-upload
- Abrir el PDF del build aislado y mirar visualmente página 1 (footer "Preprint" + nota a pie correcta).
- Confirmar que el "Online Resources"/links del paper apuntan donde deben (GitHub URL sigue provisional `gabrielireland/`).

## ⛔ NO TOCAR todavía
- **Drafts de Zenodo NO se publican** hasta camera-ready (19 ago). Citar DOIs reservados en el preprint.
- No cambiar números ni texto del paper (mantener identidad con lo enviado).

## Comando de compilación (para re-verificar)
```bash
cd paper/arxiv/arxiv_upload
PDFLATEX=/usr/local/texlive/2023/bin/universal-darwin/pdflatex   # el 2024 NO tiene totpages.sty
BIBTEX=/usr/local/texlive/2023/bin/universal-darwin/bibtex
J=geonatureagent_benchmark
"$PDFLATEX" -interaction=nonstopmode "$J.tex"; "$BIBTEX" "$J"; "$PDFLATEX" "$J.tex"; "$PDFLATEX" "$J.tex"
```
