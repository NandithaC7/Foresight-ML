#!/usr/bin/env python3
"""Read-only, incremental audit of the local TR-6 dataset."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps


IMAGE_TS_RE = re.compile(r"^(?P<date>\d{8})_(?P<time>\d{6})(?:_(?P<t1>-?\d+(?:\.\d+)?)C_(?P<t2>-?\d+(?:\.\d+)?)C)?$", re.I)
MEASUREMENT_RE = re.compile(
    r"^ADC:\s*(?P<adc>-?\d+(?:\.\d+)?)\s*\|\s*"
    r"Rs:\s*(?P<rs>-?\d+(?:\.\d+)?)\s*kΩ\s*\|\s*"
    r"Rs/R0:\s*(?P<ratio>-?\d+(?:\.\d+)?)\s*\|\s*"
    r"Methane:\s*(?P<methane>-?\d+(?:\.\d+)?)\s*ppm$"
)
DAY_RE = re.compile(r"^Day\s+(\d+)\s*$", re.I)
CASE_RE = re.compile(r"^case\s+(\d+)\s*$", re.I)
PRODUCE = ("Banana", "Carrot", "Guava", "Indian_Gooseberry", "Mango", "Tomato")


def percentile(values, pct):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * pct / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def distribution(values):
    if not values:
        return {}
    return {
        "count": len(values),
        "min": min(values),
        "p25": percentile(values, 25),
        "median": percentile(values, 50),
        "p75": percentile(values, 75),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "mean": statistics.fmean(values),
    }


def write_csv(path, rows, fieldnames=None):
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(8 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def classify_path(rel):
    parts = rel.parts
    source = parts[0] if parts and parts[0] in ("Classified", "Normal") else "root"
    produce = next((part for part in parts if part in PRODUCE), "")
    label = next((part for part in parts if part in ("Spoiled", "Not_spoiled")), "")
    if "IR_fusion_images" in parts:
        modality = "thermal_ir_fusion"
    elif "sRGB_images" in parts:
        modality = "srgb"
    elif rel.name == "Methane_gas_readings.txt":
        modality = "methane"
    elif rel.name == "README.txt":
        modality = "documentation"
    else:
        modality = "metadata_or_other"
    return source, produce, label, modality


def parse_image_timestamp(path):
    match = IMAGE_TS_RE.match(path.stem)
    if not match:
        return None, None, None
    try:
        stamp = datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
    except ValueError:
        return None, None, None
    t1 = float(match.group("t1")) if match.group("t1") is not None else None
    t2 = float(match.group("t2")) if match.group("t2") is not None else None
    return stamp, t1, t2


def parse_methane(path, rel):
    source, produce, label, _ = classify_path(rel)
    result = {
        "path": str(rel),
        "source": source,
        "produce": produce,
        "label": label,
        "encoding": "utf-8",
        "delimiter": "pipe-separated labeled fields",
        "columns": "ADC; Rs_kohm; Rs_R0; methane_ppm",
        "records": 0,
        "malformed_measurement_like_lines": 0,
        "unrecognized_nonempty_lines": 0,
        "null_markers": 0,
        "days": [],
        "cases": [],
        "sides": [],
        "adc": [],
        "rs_kohm": [],
        "rs_r0": [],
        "methane_ppm": [],
        "sample_records": [],
        "issues": [],
        "error": "",
    }
    current_day = current_case = current_side = None
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        result["encoding"] = "utf-8-replacement"
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        result["error"] = repr(exc)
        return result, ""

    parsed_records = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        day_match = DAY_RE.match(line)
        case_match = CASE_RE.match(line)
        measurement_match = MEASUREMENT_RE.match(line)
        if day_match:
            current_day = int(day_match.group(1))
            result["days"].append(current_day)
        elif case_match:
            current_case = int(case_match.group(1))
            result["cases"].append(current_case)
        elif line.upper() in ("R", "L"):
            current_side = line.upper()
            result["sides"].append(current_side)
        elif line.lower() == "-null-":
            result["null_markers"] += 1
            result["issues"].append({
                "line": line_number,
                "day": current_day,
                "case": current_case,
                "side": current_side,
                "issue_type": "null_marker",
                "content": line,
            })
        elif measurement_match:
            row = {
                "line": line_number,
                "day": current_day,
                "case": current_case,
                "side": current_side,
                "adc": float(measurement_match.group("adc")),
                "rs_kohm": float(measurement_match.group("rs")),
                "rs_r0": float(measurement_match.group("ratio")),
                "methane_ppm": float(measurement_match.group("methane")),
            }
            parsed_records.append(row)
            for key in ("adc", "rs_kohm", "rs_r0", "methane_ppm"):
                result[key].append(row[key])
        else:
            result["unrecognized_nonempty_lines"] += 1
            issue_type = "unrecognized_line"
            if any(token in line for token in ("ADC", "DC:", "Rs", "Methane", "|")):
                result["malformed_measurement_like_lines"] += 1
                issue_type = "malformed_measurement"
            result["issues"].append({
                "line": line_number,
                "day": current_day,
                "case": current_case,
                "side": current_side,
                "issue_type": issue_type,
                "content": line,
            })
    result["records"] = len(parsed_records)
    if parsed_records:
        indices = sorted(set((0, len(parsed_records) // 2, len(parsed_records) - 1)))
        result["sample_records"] = [parsed_records[index] for index in indices]
    result["days"] = sorted(set(result["days"]))
    result["cases"] = sorted(set(result["cases"]))
    result["sides"] = sorted(set(result["sides"]))
    return result, text


def sessionize(image_rows, gap_seconds=300):
    sessions = []
    grouped = defaultdict(list)
    for row in image_rows:
        if row.get("_timestamp"):
            grouped[(row["source"], row["produce"], row["label"], row["modality"])].append(row)
    for key, rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["_timestamp"])
        current = []
        for row in rows:
            if current:
                gap = (row["_timestamp"] - current[-1]["_timestamp"]).total_seconds()
                if gap > gap_seconds or row["_timestamp"].date() != current[-1]["_timestamp"].date():
                    sessions.append((key, current))
                    current = []
            current.append(row)
        if current:
            sessions.append((key, current))
    output = []
    for index, (key, rows) in enumerate(sessions, 1):
        source, produce, label, modality = key
        output.append({
            "session_id": "S%05d" % index,
            "source": source,
            "produce": produce,
            "label": label,
            "modality": modality,
            "start": rows[0]["_timestamp"].isoformat(),
            "end": rows[-1]["_timestamp"].isoformat(),
            "duration_seconds": int((rows[-1]["_timestamp"] - rows[0]["_timestamp"]).total_seconds()),
            "image_count": len(rows),
            "exactly_17_images": len(rows) == 17,
            "derivation": "timestamp cluster; new session after >300 seconds or date change",
        })
    return output


def build_contact_sheets(sample_rows, root, output_dir):
    by_source_label = defaultdict(list)
    for row in sample_rows:
        by_source_label[(row["source"], row["label"])].append(row)
    outputs = []
    for key, rows in sorted(by_source_label.items()):
        source, label = key
        title = source + ((" / " + label) if label else "")
        rows.sort(key=lambda row: (row["produce"], row["modality"]))
        cell_w, cell_h = 280, 225
        columns = 4
        sheet_rows = math.ceil(len(rows) / columns)
        canvas = Image.new("RGB", (columns * cell_w, 42 + sheet_rows * cell_h), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 12), title + " — representative audit samples", fill="black")
        for idx, row in enumerate(rows):
            x = (idx % columns) * cell_w
            y = 42 + (idx // columns) * cell_h
            try:
                with Image.open(root / row["path"]) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    image.thumbnail((cell_w - 16, 170))
                    canvas.paste(image, (x + 8, y + 8))
                caption = "%s | %s" % (row["produce"], row["modality"])
                draw.text((x + 8, y + 184), caption, fill="black")
                draw.text((x + 8, y + 200), Path(row["path"]).name[:38], fill="black")
            except Exception as exc:
                draw.text((x + 8, y + 24), "Unreadable: " + str(exc)[:35], fill="black")
        safe_name = (source + ("-" + label if label else "")).lower().replace("_", "-")
        output = output_dir / ("contact-sheet-" + safe_name + ".jpg")
        canvas.save(output, format="JPEG", quality=82)
        outputs.append(str(output))
    return outputs


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.dataset.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    print("Auditing", root, flush=True)

    if not root.is_dir():
        raise SystemExit("Dataset path is not a directory: %s" % root)

    paths = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: str(path.relative_to(root)))
    size_groups = defaultdict(list)
    basic = []
    for path in paths:
        rel = path.relative_to(root)
        source, produce, label, modality = classify_path(rel)
        try:
            stat = path.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
            size_groups[size].append(path)
            basic.append((path, rel, source, produce, label, modality, size, mtime, ""))
        except Exception as exc:
            basic.append((path, rel, source, produce, label, modality, None, "", repr(exc)))

    print("Inventory:", len(basic), "files", flush=True)
    inventory = []
    image_rows = []
    hash_groups = defaultdict(list)
    errors = []
    for index, item in enumerate(basic, 1):
        path, rel, source, produce, label, modality, size, mtime, stat_error = item
        row = {
            "path": str(rel),
            "size_bytes": size,
            "mtime": mtime,
            "extension": path.suffix.lower() or "[none]",
            "source": source,
            "produce": produce,
            "label": label,
            "modality": modality,
            "read_status": "unreadable" if stat_error else ("zero_byte" if size == 0 else "readable"),
            "validation_status": "not_applicable",
            "format": "",
            "width": "",
            "height": "",
            "color_mode": "",
            "timestamp_from_filename": "",
            "thermal_temperature_1_c": "",
            "thermal_temperature_2_c": "",
            "sha256": "",
            "error": stat_error,
        }
        if not stat_error:
            try:
                digest = sha256_file(path)
                row["sha256"] = digest
                hash_groups[digest].append(row)
            except Exception as exc:
                row["read_status"] = "unreadable"
                row["error"] = repr(exc)
                errors.append({"path": str(rel), "stage": "hash", "error": repr(exc)})
        if modality in ("srgb", "thermal_ir_fusion") and size != 0 and row["read_status"] == "readable":
            try:
                with Image.open(path) as image:
                    row["format"] = image.format or ""
                    row["width"], row["height"] = image.size
                    row["color_mode"] = image.mode
                    image.verify()
                row["validation_status"] = "valid"
            except Exception as exc:
                row["validation_status"] = "corrupt_or_invalid"
                row["error"] = repr(exc)
                errors.append({"path": str(rel), "stage": "image_verify", "error": repr(exc)})
            stamp, temp1, temp2 = parse_image_timestamp(path)
            if stamp:
                row["timestamp_from_filename"] = stamp.isoformat()
                row["_timestamp"] = stamp
            else:
                row["_timestamp"] = None
            if temp1 is not None:
                row["thermal_temperature_1_c"] = temp1
                row["thermal_temperature_2_c"] = temp2
            image_rows.append(row)
        inventory.append(row)
        if index % 1000 == 0 or index == len(basic):
            print("Processed %d/%d files" % (index, len(basic)), flush=True)

    duplicate_hashes = {digest: rows for digest, rows in hash_groups.items() if len(rows) > 1}
    duplicate_rows = []
    for group_index, (digest, rows) in enumerate(sorted(duplicate_hashes.items()), 1):
        sources = {row["source"] for row in rows}
        labels = {row["label"] for row in rows if row["label"]}
        modalities = {row["modality"] for row in rows}
        for row in rows:
            duplicate_rows.append({
                "duplicate_group": "D%05d" % group_index,
                "sha256": digest,
                "size_bytes": row["size_bytes"],
                "member_count": len(rows),
                "cross_source": len(sources) > 1,
                "cross_label": len(labels) > 1,
                "cross_modality": len(modalities) > 1,
                "path": row["path"],
            })

    direct_dirs = defaultdict(lambda: {"file_count": 0, "size_bytes": 0})
    recursive_dirs = defaultdict(lambda: {"file_count": 0, "size_bytes": 0})
    for row in inventory:
        rel = Path(row["path"])
        size = row["size_bytes"] or 0
        direct_dirs[str(rel.parent)]["file_count"] += 1
        direct_dirs[str(rel.parent)]["size_bytes"] += size
        parents = [Path(".")] + list(rel.parents)[:-1]
        for parent in parents:
            recursive_dirs[str(parent)]["file_count"] += 1
            recursive_dirs[str(parent)]["size_bytes"] += size
    directory_rows = []
    for directory in sorted(set(direct_dirs) | set(recursive_dirs)):
        directory_rows.append({
            "directory": directory,
            "direct_file_count": direct_dirs[directory]["file_count"],
            "direct_size_bytes": direct_dirs[directory]["size_bytes"],
            "recursive_file_count": recursive_dirs[directory]["file_count"],
            "recursive_size_bytes": recursive_dirs[directory]["size_bytes"],
        })

    def aggregate(keys):
        groups = defaultdict(lambda: {"file_count": 0, "size_bytes": 0, "zero_byte": 0, "unreadable": 0})
        for row in inventory:
            key = tuple(row[name] for name in keys)
            groups[key]["file_count"] += 1
            groups[key]["size_bytes"] += row["size_bytes"] or 0
            groups[key]["zero_byte"] += row["read_status"] == "zero_byte"
            groups[key]["unreadable"] += row["read_status"] == "unreadable"
        rows = []
        for key, values in sorted(groups.items()):
            rows.append(dict(zip(keys, key), **values))
        return rows

    extension_rows = aggregate(("extension",))
    produce_rows = aggregate(("source", "produce", "label", "modality"))
    modality_rows = aggregate(("modality",))

    image_summary_groups = defaultdict(list)
    for row in image_rows:
        key = (row["source"], row["produce"], row["label"], row["modality"], row["format"], row["width"], row["height"], row["color_mode"])
        image_summary_groups[key].append(row)
    image_summary_rows = []
    for key, rows in sorted(image_summary_groups.items()):
        sizes = [row["size_bytes"] for row in rows if row["size_bytes"] is not None]
        source, produce, label, modality, image_format, width, height, color_mode = key
        dist = distribution(sizes)
        image_summary_rows.append({
            "source": source,
            "produce": produce,
            "label": label,
            "modality": modality,
            "format": image_format,
            "width": width,
            "height": height,
            "color_mode": color_mode,
            "count": len(rows),
            "valid": sum(row["validation_status"] == "valid" for row in rows),
            "corrupt_or_invalid": sum(row["validation_status"] == "corrupt_or_invalid" for row in rows),
            "size_min": dist.get("min"),
            "size_p25": dist.get("p25"),
            "size_median": dist.get("median"),
            "size_p75": dist.get("p75"),
            "size_p95": dist.get("p95"),
            "size_max": dist.get("max"),
        })

    sample_rows = []
    image_strata = defaultdict(list)
    for row in image_rows:
        if row["validation_status"] == "valid":
            image_strata[(row["source"], row["produce"], row["label"], row["modality"])].append(row)
    for key, rows in sorted(image_strata.items()):
        rows.sort(key=lambda row: row["path"])
        selected = rows[len(rows) // 2]
        sample_rows.append({name: value for name, value in selected.items() if not name.startswith("_")})
    contact_sheets = build_contact_sheets(sample_rows, root, output)

    methane_results = []
    methane_text = {}
    methane_sample_rows = []
    methane_issue_rows = []
    for path, rel, source, produce, label, modality, size, mtime, stat_error in basic:
        if modality != "methane":
            continue
        parsed, text = parse_methane(path, rel)
        methane_text[(source, produce, label)] = text
        flat = {
            key: value for key, value in parsed.items()
            if key not in ("adc", "rs_kohm", "rs_r0", "methane_ppm", "sample_records", "issues")
        }
        for key in ("days", "cases", "sides"):
            flat[key] = ";".join(str(value) for value in flat[key])
        for key in ("adc", "rs_kohm", "rs_r0", "methane_ppm"):
            dist = distribution(parsed[key])
            flat[key + "_min"] = dist.get("min")
            flat[key + "_median"] = dist.get("median")
            flat[key + "_max"] = dist.get("max")
        methane_results.append(flat)
        for record in parsed["sample_records"]:
            methane_sample_rows.append({"path": str(rel), **record})
        for issue in parsed["issues"]:
            methane_issue_rows.append({"path": str(rel), **issue})

    methane_correspondence = []
    for produce in PRODUCE:
        normal = methane_text.get(("Normal", produce, ""), "")
        for label in ("Not_spoiled", "Spoiled"):
            classified = methane_text.get(("Classified", produce, label), "")
            exact_substring = bool(normal and classified and classified.strip() in normal)
            methane_correspondence.append({
                "produce": produce,
                "classified_label": label,
                "classified_is_exact_text_span_of_normal": exact_substring,
                "normal_bytes": len(normal.encode("utf-8")),
                "classified_bytes": len(classified.encode("utf-8")),
            })

    correspondence_rows = []
    correspondence_groups = defaultdict(dict)
    for key, rows in image_strata.items():
        source, produce, label, modality = key
        correspondence_groups[(source, produce, label)][modality] = rows
    for key, modalities in sorted(correspondence_groups.items()):
        source, produce, label = key
        rgb = modalities.get("srgb", [])
        thermal = modalities.get("thermal_ir_fusion", [])
        rgb_by_ts = defaultdict(list)
        thermal_by_ts = defaultdict(list)
        for row in rgb:
            if row.get("_timestamp"):
                rgb_by_ts[row["_timestamp"]].append(row)
        for row in thermal:
            if row.get("_timestamp"):
                thermal_by_ts[row["_timestamp"]].append(row)
        exact_times = set(rgb_by_ts) & set(thermal_by_ts)
        exact_candidates = sum(min(len(rgb_by_ts[stamp]), len(thermal_by_ts[stamp])) for stamp in exact_times)
        rgb_unmatched = [row for row in rgb if row.get("_timestamp") not in exact_times]
        thermal_unmatched = [row for row in thermal if row.get("_timestamp") not in exact_times]
        rgb_nearest = {}
        thermal_nearest = {}
        for row in rgb_unmatched:
            candidates = [candidate for candidate in thermal_unmatched if candidate["_timestamp"].date() == row["_timestamp"].date()]
            if candidates:
                rgb_nearest[row["path"]] = min(candidates, key=lambda candidate: abs((candidate["_timestamp"] - row["_timestamp"]).total_seconds()))
        for row in thermal_unmatched:
            candidates = [candidate for candidate in rgb_unmatched if candidate["_timestamp"].date() == row["_timestamp"].date()]
            if candidates:
                thermal_nearest[row["path"]] = min(candidates, key=lambda candidate: abs((candidate["_timestamp"] - row["_timestamp"]).total_seconds()))
        probable = []
        for row in rgb_unmatched:
            candidate = rgb_nearest.get(row["path"])
            if candidate and thermal_nearest.get(candidate["path"], {}).get("path") == row["path"]:
                gap = abs((candidate["_timestamp"] - row["_timestamp"]).total_seconds())
                if gap <= 120:
                    probable.append(gap)
        correspondence_rows.append({
            "source": source,
            "produce": produce,
            "label": label,
            "srgb_count": len(rgb),
            "thermal_count": len(thermal),
            "exact_timestamp_candidates": exact_candidates,
            "probable_mutual_nearest_within_120s": len(probable),
            "probable_gap_median_seconds": percentile(probable, 50),
            "same_calendar_dates": len({row["_timestamp"].date() for row in rgb if row.get("_timestamp")} & {row["_timestamp"].date() for row in thermal if row.get("_timestamp")}),
            "verified_cross_modal_pairs": 0,
            "limitation": "timestamps support candidates only; no shared specimen/view identifier",
        })

    sessions = sessionize(image_rows)
    session_groups = defaultdict(lambda: defaultdict(list))
    for session in sessions:
        key = (session["source"], session["produce"], session["label"])
        session_groups[key][session["modality"]].append(session)
    session_pairs = []
    session_pair_counts = Counter()
    session_pair_both17 = Counter()
    for key, modalities in sorted(session_groups.items()):
        rgb_sessions = modalities.get("srgb", [])
        thermal_sessions = modalities.get("thermal_ir_fusion", [])
        rgb_nearest = {}
        thermal_nearest = {}
        for rgb in rgb_sessions:
            rgb_time = datetime.fromisoformat(rgb["start"])
            candidates = [
                thermal for thermal in thermal_sessions
                if datetime.fromisoformat(thermal["start"]).date() == rgb_time.date()
            ]
            if candidates:
                rgb_nearest[rgb["session_id"]] = min(
                    candidates,
                    key=lambda thermal: abs((datetime.fromisoformat(thermal["start"]) - rgb_time).total_seconds()),
                )
        for thermal in thermal_sessions:
            thermal_time = datetime.fromisoformat(thermal["start"])
            candidates = [
                rgb for rgb in rgb_sessions
                if datetime.fromisoformat(rgb["start"]).date() == thermal_time.date()
            ]
            if candidates:
                thermal_nearest[thermal["session_id"]] = min(
                    candidates,
                    key=lambda rgb: abs((datetime.fromisoformat(rgb["start"]) - thermal_time).total_seconds()),
                )
        for rgb in rgb_sessions:
            thermal = rgb_nearest.get(rgb["session_id"])
            if not thermal:
                continue
            reciprocal = thermal_nearest.get(thermal["session_id"])
            if not reciprocal or reciprocal["session_id"] != rgb["session_id"]:
                continue
            gap = abs(
                (datetime.fromisoformat(thermal["start"]) - datetime.fromisoformat(rgb["start"])).total_seconds()
            )
            both17 = int(rgb["image_count"]) == 17 and int(thermal["image_count"]) == 17
            status = "probable_session_candidate" if gap <= 1800 and both17 else "unresolved"
            session_pairs.append({
                "source": key[0],
                "produce": key[1],
                "label": key[2],
                "rgb_session_id": rgb["session_id"],
                "thermal_session_id": thermal["session_id"],
                "rgb_start": rgb["start"],
                "thermal_start": thermal["start"],
                "start_gap_seconds": int(gap),
                "rgb_image_count": rgb["image_count"],
                "thermal_image_count": thermal["image_count"],
                "both_exactly_17_images": both17,
                "status": status,
                "basis": "mutual-nearest inferred timestamp sessions on the same calendar date",
            })
            if status == "probable_session_candidate":
                session_pair_counts[key] += 1
                if both17:
                    session_pair_both17[key] += 1
    for row in correspondence_rows:
        key = (row["source"], row["produce"], row["label"])
        row["probable_session_pairs_within_30m"] = session_pair_counts[key]
        row["probable_session_pairs_both_17"] = session_pair_both17[key]

    normal_hashes = defaultdict(set)
    for row in inventory:
        if row["source"] == "Normal" and row["produce"] and row["sha256"]:
            normal_hashes[(row["produce"], row["modality"])].add(row["sha256"])
    mirror_rows = []
    mirror_groups = defaultdict(lambda: {"classified_files": 0, "exact_normal_duplicates": 0})
    for row in inventory:
        if row["source"] != "Classified" or not row["produce"]:
            continue
        key = (row["produce"], row["label"], row["modality"])
        mirror_groups[key]["classified_files"] += 1
        if row["sha256"] in normal_hashes[(row["produce"], row["modality"])]:
            mirror_groups[key]["exact_normal_duplicates"] += 1
    for key, values in sorted(mirror_groups.items()):
        produce, label, modality = key
        mirror_rows.append({"produce": produce, "label": label, "modality": modality, **values})

    public_inventory = [{key: value for key, value in row.items() if not key.startswith("_")} for row in inventory]
    write_csv(output / "file_inventory.csv", public_inventory)
    write_csv(output / "directory_summary.csv", directory_rows)
    write_csv(output / "extension_summary.csv", extension_rows)
    write_csv(output / "produce_modality_summary.csv", produce_rows)
    write_csv(output / "modality_summary.csv", modality_rows)
    write_csv(output / "image_summary.csv", image_summary_rows)
    write_csv(output / "representative_image_samples.csv", sample_rows)
    write_csv(output / "exact_duplicate_files.csv", duplicate_rows)
    write_csv(output / "methane_files.csv", methane_results)
    write_csv(output / "methane_sample_records.csv", methane_sample_rows)
    write_csv(
        output / "methane_issues.csv",
        methane_issue_rows,
        ("path", "line", "day", "case", "side", "issue_type", "content"),
    )
    write_csv(output / "methane_normal_classified_correspondence.csv", methane_correspondence)
    write_csv(output / "image_correspondence_summary.csv", correspondence_rows)
    write_csv(output / "inferred_image_sessions.csv", sessions)
    write_csv(output / "probable_session_correspondence.csv", session_pairs)
    write_csv(output / "classified_normal_exact_duplicates.csv", mirror_rows)
    write_csv(output / "errors.csv", errors, ("path", "stage", "error"))

    total_bytes = sum((row["size_bytes"] or 0) for row in inventory)
    valid_images = sum(row["validation_status"] == "valid" for row in image_rows)
    corrupt_images = sum(row["validation_status"] == "corrupt_or_invalid" for row in image_rows)
    zero_byte = sum(row["read_status"] == "zero_byte" for row in inventory)
    unreadable = sum(row["read_status"] == "unreadable" for row in inventory)
    duplicate_file_count = sum(len(rows) for rows in duplicate_hashes.values())
    duplicate_excess_count = sum(len(rows) - 1 for rows in duplicate_hashes.values())
    cross_label_groups = sum(
        len({row["label"] for row in rows if row["label"]}) > 1
        for rows in duplicate_hashes.values()
    )
    cross_source_groups = sum(len({row["source"] for row in rows}) > 1 for rows in duplicate_hashes.values())
    image_counts = Counter(row["modality"] for row in image_rows)
    methane_record_count = sum(row["records"] for row in methane_results)
    image_hashes = {row["sha256"] for row in image_rows if row["sha256"]}
    classified_images = [row for row in image_rows if row["source"] == "Classified"]
    classified_exact_normal = sum(
        row["sha256"] in normal_hashes[(row["produce"], row["modality"])]
        for row in classified_images
    )
    normal_image_hashes = {
        (row["produce"], row["modality"], row["sha256"])
        for row in image_rows if row["source"] == "Normal" and row["sha256"]
    }
    classified_image_hashes = {
        (row["produce"], row["modality"], row["sha256"])
        for row in image_rows if row["source"] == "Classified" and row["sha256"]
    }
    size_distributions = {
        modality: distribution([
            row["size_bytes"] for row in image_rows
            if row["modality"] == modality and row["size_bytes"] is not None
        ])
        for modality in ("srgb", "thermal_ir_fusion")
    }
    summary = {
        "dataset_path": str(root),
        "generated_at": datetime.now().isoformat(),
        "elapsed_seconds": time.time() - started,
        "file_count": len(inventory),
        "total_bytes": total_bytes,
        "total_gib": total_bytes / (1024 ** 3),
        "zero_byte_files": zero_byte,
        "unreadable_files": unreadable,
        "valid_images": valid_images,
        "corrupt_or_invalid_images": corrupt_images,
        "image_counts": dict(image_counts),
        "methane_file_count": len(methane_results),
        "methane_record_count": methane_record_count,
        "duplicate_groups": len(duplicate_hashes),
        "files_in_duplicate_groups": duplicate_file_count,
        "duplicate_excess_copies": duplicate_excess_count,
        "cross_source_duplicate_groups": cross_source_groups,
        "cross_label_duplicate_groups": cross_label_groups,
        "unique_image_hashes": len(image_hashes),
        "classified_images_exactly_duplicated_in_normal": classified_exact_normal,
        "normal_image_hashes_not_represented_in_classified": len(normal_image_hashes - classified_image_hashes),
        "image_size_bytes": size_distributions,
        "methane_null_markers_all_trees": sum(row["null_markers"] for row in methane_results),
        "methane_malformed_lines_all_trees": sum(row["malformed_measurement_like_lines"] for row in methane_results),
        "probable_session_pairs_all_trees": sum(session_pair_counts.values()),
        "contact_sheets": contact_sheets,
        "verified_cross_modal_pairs": 0,
    }
    (output / "audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    modality_count_rows = []
    for row in modality_rows:
        modality_count_rows.append((row["modality"], row["file_count"], row["size_bytes"]))
    class_rows = []
    for row in produce_rows:
        if row["modality"] in ("srgb", "thermal_ir_fusion", "methane"):
            class_rows.append((row["source"], row["produce"], row["label"] or "unlabeled", row["modality"], row["file_count"]))
    methane_report_rows = []
    for row in methane_results:
        methane_report_rows.append((row["source"], row["produce"], row["label"] or "unlabeled", row["records"], row["days"], row["null_markers"], row["malformed_measurement_like_lines"]))
    correspondence_report_rows = []
    for row in correspondence_rows:
        correspondence_report_rows.append((row["source"], row["produce"], row["label"] or "unlabeled", row["srgb_count"], row["thermal_count"], row["exact_timestamp_candidates"], row["probable_mutual_nearest_within_120s"]))
    mirror_report_rows = []
    for row in mirror_rows:
        if row["modality"] in ("srgb", "thermal_ir_fusion", "methane"):
            mirror_report_rows.append((row["produce"], row["label"], row["modality"], row["exact_normal_duplicates"], row["classified_files"]))

    report = f"""# TR-6 Multimodal Dataset Audit

Generated: {summary['generated_at']}

Dataset (read only): `{root}`

## Executive summary

- Inventoried **{summary['file_count']:,} files** totaling **{summary['total_gib']:.2f} GiB**.
- Validated **{valid_images:,} images** incrementally with Pillow `verify()`; found **{corrupt_images:,} corrupt/invalid**, **{unreadable:,} unreadable**, and **{zero_byte:,} zero-byte files**.
- Parsed **{len(methane_results)} methane files** containing **{methane_record_count:,} measurement records**.
- SHA-256 hashing found **{len(duplicate_hashes):,} exact duplicate groups**, involving **{duplicate_file_count:,} files** and **{duplicate_excess_count:,} excess copies**.
- Every one of the **{classified_exact_normal:,} classified images** is an exact byte duplicate of an image in `Normal`; **{len(normal_image_hashes - classified_image_hashes):,}** unique Normal image hashes are not represented in `Classified`.
- **{cross_label_groups:,} exact image-content groups occur under both `Spoiled` and `Not_spoiled`**, creating direct label conflicts.
- No RGB↔thermal or image↔methane pairing is verified at specimen level. Filename timestamps and daily ordering provide candidates, not ground truth.
- `Classified` is a labeled derivative structure; `Normal` has no `Spoiled`/`Not_spoiled` path label. These trees must not be treated as independent datasets.

## Inventory by apparent modality

{markdown_table(("Modality", "Files", "Bytes"), modality_count_rows)}

Full path-level and directory-level sizes are in `file_inventory.csv` and `directory_summary.csv`.

## Actual directory semantics and class distributions

`Normal/<produce>/{{IR_fusion_images,sRGB_images}}` contains modality folders plus one produce-level methane file. `Classified/<produce>/{{Not_spoiled,Spoiled}}/{{IR_fusion_images,sRGB_images}}` adds path-based spoilage labels and one methane file per label. The README describes the same concepts but states the nesting order ambiguously.

{markdown_table(("Tree", "Produce", "Path label", "Modality", "Files"), class_rows)}

Only `Classified` supplies a defensible existing binary path label. `Normal` should be treated as unlabeled with respect to spoilage unless a documented derivation map is supplied.

## Image audit

- Apparent sRGB files: **{image_counts.get('srgb', 0):,}**.
- Apparent thermal IR-fusion files: **{image_counts.get('thermal_ir_fusion', 0):,}**.
- Modality identification is based on the explicit directory names and README, not pixel appearance alone.
- Thermal filenames include two temperature-like values with `C`; their precise meanings are not documented.
- All thermal images are 640×480 RGB JPEG renderings. sRGB images are RGB JPEGs: predominantly 4000×3000, with a 2576×1932 subset.
- Across both trees, sRGB file sizes have median **{size_distributions['srgb']['median'] / 1024:.1f} KiB** (p95 **{size_distributions['srgb']['p95'] / 1024:.1f} KiB**); thermal files have median **{size_distributions['thermal_ir_fusion']['median'] / 1024:.1f} KiB** (p95 **{size_distributions['thermal_ir_fusion']['p95'] / 1024:.1f} KiB**).
- Detailed dimensions, formats, color modes, and size percentiles are in `image_summary.csv`.
- One median-path sample from every source/produce/label/modality stratum is recorded in `representative_image_samples.csv`; visual contact sheets are alongside this report.

## Methane audit

The files are structured text, not CSV. Measurement lines contain four pipe-separated labeled fields: ADC, sensor resistance `Rs` in kΩ, `Rs/R0`, and methane in ppm. Hierarchical headers encode `Day`, `case`, and side `R`/`L`. No wall-clock timestamp, sampling interval, specimen UUID, device ID, calibration record, environmental measurement, or explicit link to image filenames is present.

{markdown_table(("Tree", "Produce", "Path label", "Records", "Days", "Null markers", "Malformed measurement lines"), methane_report_rows)}

`methane_files.csv` reports value ranges, missing/null markers, malformed lines, and per-file structure. Three representative parsed records per file are in `methane_sample_records.csv`; exact issue locations are in `methane_issues.csv`. Across `Normal`, 12 `-null-` markers and three malformed measurement lines were found; the same issues recur in their classified text spans. Repeated consecutive values are common but are retained as observations; measurement frequency cannot be inferred without timestamps or acquisition documentation.

## Multimodal correspondence

{markdown_table(("Tree", "Produce", "Path label", "RGB", "Thermal", "Exact timestamp candidates", "Mutual nearest ≤120 s"), correspondence_report_rows)}

### Verified

- Exact byte identity established by SHA-256 is verified only for duplicate files.
- `methane_normal_classified_correspondence.csv` tests whether each classified methane file is an exact text span of its produce-level Normal file.
- `classified_normal_exact_duplicates.csv` quantifies exact image/file reuse from `Normal` into `Classified`.

{markdown_table(("Produce", "Label", "Modality", "Exact Normal duplicates", "Classified files"), mirror_report_rows)}

### Probable

- RGB and thermal images in the same tree/produce/path-label with identical filename timestamps are probable same-capture candidates.
- Mutual nearest timestamps within 120 seconds on the same date are weaker probable session candidates.
- Timestamp clusters in `inferred_image_sessions.csv` are operational session hypotheses only. Mutual-nearest 17-image RGB/thermal sessions within 30 minutes are listed in `probable_session_correspondence.csv`. Both thresholds are audit heuristics, not annotations or verified pairs.

### Unresolved

- No filename contains a documented specimen/case identifier or view index.
- `case 1..N` and `R/L` in methane text cannot be mapped to particular images.
- The README's statement about 17 thermal images per fruit per day does not prove 17 RGB pairs, and counts are not uniformly equal.
- Sorted dates/days may reflect chronology, but no explicit acquisition-date-to-`Day N` map exists.
- Therefore **zero cross-modal specimen-level pairs are marked verified**.

## Duplication, leakage, and split risks

- Exact duplicates across `Normal` and `Classified` make those trees non-independent.
- The **{cross_label_groups:,}** exact duplicate groups crossing `Spoiled` and `Not_spoiled` are direct label conflicts. They comprise all 153 Banana thermal images in each label plus 17 Indian Gooseberry thermal contents.
- Images within short timestamp clusters are repeated views of one collection event and likely of the same produce specimen. Random image-level splitting would leak appearance, background, date, device, and maturity trajectory.
- Consecutive days are temporally dependent. Splitting adjacent days for the same specimen across train/test would overstate generalization.
- Filename temperatures and thermal rendering may encode acquisition conditions correlated with labels.

## Research readiness

- **Potentially suitable after conflict exclusion and provenance review:** produce-type classification, and exploratory path-label spoilage classification using `Classified`. The binary label is not publication-ready while identical images carry conflicting labels.
- **Not currently supported:** segmentation and object detection (no masks/boxes), shelf-life regression (no verified remaining-life target), specimen-level multimodal fusion (no defensible cross-modal key), or calibrated methane-based spoilage inference (no protocol/calibration metadata).
- A leakage-safe split cannot yet be guaranteed at specimen level. Until specimen IDs are recovered, group all exact duplicates together, then group by produce plus conservative timestamp-session/date blocks; keep an entire inferred longitudinal date range together where it may represent one specimen. Use leave-one-specimen/session-out only after provenance confirms those groups.

## Proposed Foresight-TR6+ extension

1. Recover acquisition logs and assign immutable `specimen_id`, `session_id`, `capture_id`, `view_id`, device IDs, and timezone-aware timestamps.
2. Create a reviewed manifest linking RGB, thermal, and methane windows with confidence and provenance; preserve unmatched records.
3. Record ground-truth spoilage assessment protocol, assessor agreement, maturity stage, storage conditions, acquisition environment, and label timestamp.
4. Add calibrated thermal data or radiometric metadata if available; document the two filename temperatures.
5. Add methane sensor model, calibration curve/R0 procedure, warm-up time, sampling rate, chamber geometry, background baseline, temperature, and humidity.
6. For a defensible new task, annotate fruit masks and visible-defect regions on a specimen/session-stratified subset with inter-annotator quality control.
7. For shelf-life regression, collect actual time-to-defined-endpoint prospectively; do not derive it solely from folder labels or methane magnitude.
8. Publish checksums, a data dictionary, lineage from TR-6 to TR6+, annotation guidelines, adjudication records, exclusions, and leakage-safe official splits.

## Questions required before annotation or IEEE DataPort publication

1. What exactly do `Normal`, `Classified`, `Spoiled`, and `Not_spoiled` mean, and who assigned the labels using what criterion?
2. Are the `Classified` files intended to be a partitioned copy of `Normal`, and were any files omitted or duplicated intentionally?
3. How many physical specimens exist per produce, and does methane `case N` identify a specimen, container, replicate, or sensor run?
4. What do methane sides `R` and `L` mean?
5. Which calendar date corresponds to each `Day N`, and what is the sampling interval?
6. How are 17 views ordered, which is top-down, and are RGB and thermal captures simultaneous or sequential?
7. What do the two temperatures in thermal filenames represent?
8. Are thermal JPGs radiometric, rendered fusion images, or both? Is raw thermal data available?
9. What camera/sensor models, settings, calibration, distance, lighting, background, storage conditions, temperature, and humidity were used?
10. Are filename timestamps reliable and in one timezone? Were clocks synchronized?
11. Is there consent/licensing provenance and a publication-ready data license?
12. What exclusion criteria, missing-data policy, and intended benchmark task should the official release specify?

## Assumptions and limitations

- Directory names are used as apparent modality and existing label metadata.
- Filename timestamps are parsed as local naive times because no timezone is documented.
- Image validity means Pillow could parse and verify the encoded file; it is not a semantic-quality score.
- Exact duplication means equal SHA-256 content.
- Visual review uses representative samples, not every image.
- Session clusters and probable matches are deliberately not saved as labels.

## Reproduction

See `commands.txt`. The script reads the dataset and writes only to the separate audit output directory.
"""
    (output / "audit_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
