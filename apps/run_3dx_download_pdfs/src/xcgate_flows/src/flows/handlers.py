from __future__ import annotations

from ..io.result_summary import (
    generate_html_summary,
    open_html_summary,
    summarize_and_print,
)


class FlowHandler:
    def on_finish(self, browser_ctx, cfg, run_started_at):
        raise NotImplementedError


class CsvSummaryHandler(FlowHandler):
    def __init__(self, summary_kind: str):
        self.summary_kind = summary_kind

    def on_finish(self, browser_ctx, cfg, run_started_at):
        try:
            csv_path = cfg["logging"].get("csv_path")
            logs_dir = cfg["logging"].get("shots_dir", "logs")
            summarize_and_print(csv_path, logs_dir, run_started_at, summary_kind=self.summary_kind)
            html_path = generate_html_summary(csv_path, logs_dir, run_started_at, summary_kind=self.summary_kind)
            print(f"\n[SUMMARY] サマリーレポートを開きます: {html_path}")
            open_html_summary(html_path)
        except Exception:
            pass


FLOW_HANDLER_MAP = {
    "3dx_create_ids.flow": CsvSummaryHandler("3dx_doc"),
    "3dx_download_pdfs.flow": CsvSummaryHandler("3dx_pdf"),
    "xcgate_upload.flow": CsvSummaryHandler("xcgate"),
}


def get_flow_handler(flow_name: str) -> FlowHandler:
    return FLOW_HANDLER_MAP.get(flow_name, CsvSummaryHandler("generic"))
