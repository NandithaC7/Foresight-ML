# Test report — executed 2026-10-15

Every row below was **executed**. Evidence is in `artifacts/report/evidence/`.
The model version is `vit_b16_primary@epoch9`, and the environment is Python 3.11.16, torch 2.14.1 and Node 24.19.0 on an Apple M5.

## Summary
| Suite | Command | Result | Evidence |
|---|---|---|---|
| Backend + ML automated tests | `.venv/bin/python -m pytest backend/tests ml/tests -v` | **33 passed, 0 failed, 0 skipped** | `pytest_final.log` |
| Frontend production build | `cd frontend && npm run build` | **built** (45 modules, 204 kB JS) | `frontend_build.log` |
| Local end-to-end smoke (servers running) | `.venv/bin/python scripts/e2e_smoke.py --n 60` | **11/11 checks passed** | `e2e_smoke.log`, `e2e_smoke_final.json`, `latency_benchmark.json` |
| Browser UI checks (in-app browser) | manual steps below | **passed** | this file |

## Automated tests (pytest)
| ID | Requirement | Test | Result |
|---|---|---|---|
| B01 | Health reports the model state | `test_health_reports_loaded_model` | PASS |
| B02 | Honest model statuses (U-Net unavailable, shelf-life disabled) | `test_models_lists_honest_statuses` | PASS |
| B03 | Real-inference response contract; no fabricated shelf-life or decay values | `test_analyze_valid_jpeg_returns_real_inference_contract` | PASS |
| B04 | Deterministic inference | `test_analyze_is_deterministic` | PASS |
| B05 | PNG and WEBP accepted | `test_analyze_png_and_webp` | PASS |
| B06 | XAI overlay returned | `test_xai_overlay` | PASS |
| B07 | Wrong media type → 415 | `test_rejects_wrong_media_type` | PASS |
| B08 | Corrupt image → 400 | `test_rejects_corrupt_image` | PASS |
| B09 | Empty file → 400 | `test_rejects_empty_file` | PASS |
| B10 | Too-small image → 400 | `test_rejects_tiny_image` | PASS |
| B11 | Undecodable or unsupported format (GIF) → 400 | `test_rejects_unsupported_decoded_format` | PASS |
| B12 | Missing field → 422 with a structured error | `test_missing_field_is_422` | PASS |
| B13 | Oversized upload → 413 | `test_oversized_upload_413` | PASS |
| B14 | **Missing checkpoint fails clearly**: 503 `model_unavailable`, nothing stored | `test_missing_checkpoint_fails_clearly` | PASS |
| B15 | Mock mode off by default; when on, labelled DEMO MOCK DATA everywhere | `test_mock_mode_is_explicitly_labelled` | PASS |
| B16 | History persists across an app restart; detail endpoint; 404; clear | `test_history_persists_and_is_queryable` | PASS |
| B17 | Report text and PDF | `test_report_text_and_pdf` | PASS |
| B18 | Nutrition and tips endpoints | `test_nutrition_and_tips` | PASS |
| B19 | CORS allows configured origins only | `test_cors_allows_dev_origin_only` | PASS |
| R01 | Real checkpoint loads (not the tiny fixture) | `test_real_model_loads` | PASS |
| R02 | Real inference on 12 held-out full-resolution originals (one per stratum) | `test_real_inference_on_held_out_source_images` | PASS |
| R03 | API preprocessing matches the training cache (mean abs diff < 3/255) | `test_backend_preprocessing_matches_training_cache` | PASS |
| R04 | PNG of a real image plus XAI | `test_png_upload_of_real_image` | PASS |
| M01 | Manifest schema; one row per content | `test_manifest_schema` | PASS |
| M02 | Eligible labels valid; specimen IDs never invented | `test_eligible_rows_have_valid_labels` | PASS |
| M03 | 170 conflicting contents excluded | `test_conflicting_labels_excluded` | PASS |
| M04 | No duplicate or session leakage across splits | `test_no_leakage_between_splits` | PASS |
| M05 | 60/20/20 within ±2%; summary matches the manifest | `test_split_fractions_close_to_60_20_20` | PASS |
| M06 | Every produce×label stratum in every split | `test_every_stratum_in_every_split` | PASS |
| M07 | Source files unchanged (SHA-256 re-hash of a sample) | `test_source_files_unchanged` | PASS |
| M08 | Corruptions deterministic and correctly scaled | `test_corruptions_are_deterministic_and_bounded` | PASS |
| M09 | Model forward shapes | `test_model_forward_shapes` | PASS |
| M10 | GAN outputs marked synthetic and stored separately | `test_gan_outputs_marked_synthetic_and_train_only` | PASS |

API tests B01–B19 use a tiny **randomly initialised** checkpoint to exercise the code paths quickly. It is never used for any metric. R01–R04 use the real checkpoint.

## End-to-end smoke (real HTTP, uvicorn :8000 + Vite :5173)
| ID | Check | Result |
|---|---|---|
| E01 | Frontend serves the app | PASS |
| E02 | Backend health: real model loaded, mock off | PASS |
| E03 | CORS preflight allows the frontend origin | PASS |
| E04 | `/api/models` shows ViT loaded and U-Net unavailable | PASS |
| E05 | 60 held-out full-resolution TR-6 originals sent through HTTP | PASS: produce 60/60 correct, spoilage 57/60 correct |
| E06 | History grew by exactly 60 | PASS |
| E07 | `/api/history/{scan_id}` | PASS |
| E08 | XAI overlay | PASS |
| E09 | Wrong type → 415 with a structured error | PASS |
| E10 | Corrupt image → 400 | PASS |
| E11 | PDF report | PASS |

**Latency** (end to end, including a ~1.9 MB upload, MPS): median **38 ms**, p95 48 ms with the GPU idle. An earlier run, while training jobs shared the GPU, had a median of 91 ms.

## Browser UI verification (in-app browser, http://localhost:5173)
- **Real result:** one held-out test image (a Banana/Spoiled original) was uploaded through the real `<input type=file>`.
  - The card showed "Banana · Spoiled (100%)", produce confidence 100%, "Decay coverage: Pending annotation" and "Shelf-life left: Not available".
  - The model version, inference time, warnings and disclaimer were shown, along with an attention-rollout image focused on the fruit. **PASS.**
  - The image was served temporarily from `frontend/public/__e2e_tmp/` and deleted afterwards.
- **Corrupt upload:** the UI showed "The file could not be decoded as an image (corrupt or not an image)." **PASS.**
- **Model unavailable** (backend restarted with a non-existent checkpoint): the banner and the error both showed "Model unavailable: Checkpoint not found…", and no results were rendered. **PASS.**
- **Backend down:** the UI showed "Could not reach the analysis backend at http://localhost:8000…". **PASS.**
  This check found a missing space in the banner text, which was fixed and the UI rebuilt.
- **History, Dashboard and About** pages render persisted real scans and live `/api/models` data, with no console errors. **PASS.**

## Not tested
- Third-party deployment: no deployment was performed.
- Mobile camera capture on a physical phone.
- Real-world (non-TR-6) photos: no labelled set is available.
- Load or concurrency testing beyond sequential requests.
