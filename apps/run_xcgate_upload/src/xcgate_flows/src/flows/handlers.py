from __future__ import annotations
import datetime

from ..io.result_summary import (
    summarize_and_print,
    generate_html_summary,
    open_html_summary,
)
from ..io.summary_3dx import generate_doc_id_summary, load_doc_records_from_log, DOC_IDS_LOG


class FlowHandler:
    def on_finish(self, browser_ctx, cfg, run_started_at):
        raise NotImplementedError


class DefaultFlowHandler(FlowHandler):
    def on_finish(self, browser_ctx, cfg, run_started_at):
        try:
            summarize_and_print(
                cfg["logging"].get("csv_path"),
                cfg["logging"].get("shots_dir", "logs"),
                run_started_at,
            )
            html_path = generate_html_summary(
                cfg["logging"].get("csv_path"),
                cfg["logging"].get("shots_dir", "logs"),
                run_started_at,
            )
            print(f"\n[SUMMARY] ブラウザでサマリーレポートを開きます: {html_path}")
            open_html_summary(html_path)
        except Exception:
            pass


class Flow3DXHandler(FlowHandler):
    def on_finish(self, browser_ctx, cfg, run_started_at):
        records = getattr(browser_ctx, "doc_records", []) or load_doc_records_from_log(
            cfg["logging"].get("doc_log_path", DOC_IDS_LOG), run_started_at
        )
        if records:
            print("\n[DOC_IDS] Newly created documents:")
            for rec in records:
                doc_id = rec.get("id") or "(unknown)"
                ts = rec.get("timestamp")
                if isinstance(ts, datetime.datetime):
                    ts_txt = ts.isoformat(sep=" ")
                else:
                    ts_txt = str(ts or "")
                print(f" - {doc_id} @ {ts_txt}")
        else:
            print("\n[DOC_IDS] No documents were recorded during this run.")
        try:
            html_path = generate_doc_id_summary(
                records,
                cfg["logging"].get("shots_dir", "logs"),
                run_started_at,
            )
            if html_path:
                print(f"\n[3DX SUMMARY] {html_path}")
                open_html_summary(html_path)
        except Exception:
            pass


FLOW_HANDLER_MAP = {
    "3dx_create_ids.flow": Flow3DXHandler(),
    "xcgate_upload.flow": DefaultFlowHandler(),
}


def get_flow_handler(flow_name: str) -> FlowHandler:
    return FLOW_HANDLER_MAP.get(flow_name, DefaultFlowHandler())
