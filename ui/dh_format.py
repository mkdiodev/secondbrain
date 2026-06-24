"""Formatting helpers for drillhole validation chat output."""

from __future__ import annotations

from typing import Any


def format_drillhole_summary(summary: Any) -> str:
    total_findings = summary.total_errors + summary.total_warnings
    lines = [
        "# Hasil Validasi Drillhole",
        "",
        "## Ringkasan",
        "",
        "| Metrik | Jumlah |",
        "| --- | ---: |",
        f"| Critical errors | {summary.total_errors} |",
        f"| Warnings | {summary.total_warnings} |",
        f"| Total error/warning | {total_findings} |",
    ]
    if summary.report_path:
        lines.extend(["", f"Report: `{summary.report_path}`"])
    if not summary.errors:
        lines.extend(["", "Tidak ada error validasi."])
        return "\n".join(lines)

    lines.extend(
        [
            "",
            "## Tabel Error",
            "",
            "| Nama File | SITE_ID/HOLE_ID | Tipe Error | Kolom | Nilai/Penyebab |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for error in summary.errors:
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(getattr(error, "file_name", "") or error.table),
                    _cell(error.site_id),
                    _cell(_error_type(error)),
                    _cell(error.column or ""),
                    _cell(_error_cause(error.message)),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _error_type(error: Any) -> str:
    message = str(error.message or "")
    if ":" in message:
        return message.split(":", 1)[0].strip()
    return str(error.type or "")


def _error_cause(message: str) -> str:
    if ":" in message:
        return message.split(":", 1)[1].strip()
    return message.strip()


def _cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"
