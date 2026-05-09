use crate::app_studio_commands::AppStudioRunResult;
use crate::app_studio_result_reader::AppStudioResultSummary;
use std::path::Path;

pub(crate) fn result_from_process(
    ok: bool,
    exit_code: i32,
    stdout: String,
    stderr: String,
    summary: AppStudioResultSummary,
    process_wall_clock_seconds: Option<f64>,
    success_message: &str,
) -> AppStudioRunResult {
    let user_message = if ok {
        success_message.to_string()
    } else if summary.apply_blocked_by_secret_scan || summary.secret_blocking_count > 0 {
        format!(
            "Secret scan blocked Apply. blocking={}, warnings={}, manual_checks={}. Review secret_scan_report.md.",
            summary.secret_blocking_count, summary.secret_warning_count, summary.secret_manual_check_count
        )
    } else if summary.execution_status.as_deref() == Some("warn")
        && summary.approval_allowed == Some(true)
    {
        "App Studio completed with warnings. execution_test_result.json allows approval; review the logs before approving.".to_string()
    } else if summary.execution_status.as_deref() == Some("pass") {
        "App Studio process returned a non-zero exit code, but execution checks passed. Review stdout/stderr before approval.".to_string()
    } else {
        "App Studio processing failed. Review stdout/stderr and generated reports.".to_string()
    };
    AppStudioRunResult {
        ok,
        exit_code,
        stdout,
        stderr,
        user_message,
        output_dir: summary.output_dir,
        app_id: summary.app_id,
        selected_build_mode: summary.selected_build_mode,
        execution_status: summary.execution_status,
        approval_allowed: summary.approval_allowed,
        runtime_status: summary.runtime_status,
        app_pack: summary.app_pack,
        enabled: summary.enabled,
        current_version: None,
        new_version: summary.version,
        metadata_override_used: summary.metadata_override_used,
        metadata_override_keys: summary.metadata_override_keys,
        icon_override_used: summary.icon_override_used,
        selected_icon_source: summary.selected_icon_source,
        exe_readiness_status: summary.exe_readiness_status,
        manual_checks: summary.manual_checks,
        secret_blocking_count: summary.secret_blocking_count,
        secret_warning_count: summary.secret_warning_count,
        secret_manual_check_count: summary.secret_manual_check_count,
        secret_scan_report: summary.secret_scan_report,
        secret_blocking_findings: summary.secret_blocking_findings,
        ai_blocked_by_secret_scan: summary.ai_blocked_by_secret_scan,
        apply_blocked_by_secret_scan: summary.apply_blocked_by_secret_scan,
        approval_blocking_warnings_count: summary.approval_blocking_warnings_count,
        non_blocking_warnings_count: summary.non_blocking_warnings_count,
        info_count: summary.info_count,
        unresolved_distribution_risks_count: summary.unresolved_distribution_risks_count,
        approval_blocking_reasons: summary.approval_blocking_reasons,
        non_blocking_warning_summaries: summary.non_blocking_warning_summaries,
        timing_report: summary.timing_report,
        timing_total_seconds: summary.timing_total_seconds.or(process_wall_clock_seconds),
        timing_estimated_total_seconds: summary.timing_estimated_total_seconds,
        timing_actual_total_seconds: summary.timing_actual_total_seconds,
        timing_prediction_error_seconds: summary.timing_prediction_error_seconds,
        timing_prediction_source: summary.timing_prediction_source,
        timing_wall_clock_total_seconds: summary.timing_wall_clock_total_seconds,
        timing_cli_measured_total_seconds: summary.timing_cli_measured_total_seconds,
        timing_unmeasured_overhead_seconds: summary.timing_unmeasured_overhead_seconds,
        timing_phases: summary.timing_phases,
        process_wall_clock_seconds,
        manifest_enabled: summary.manifest_enabled,
        approval_record_status: summary.approval_record_status,
        approval_record_path: summary.approval_record_path,
        approval_failure_summary: summary.approval_failure_summary,
        verify_release_status: summary.verify_release_status,
        verify_release_failure_summary: summary.verify_release_failure_summary,
        catalog_visible: summary.catalog_visible,
        catalog_enabled: summary.catalog_enabled,
        catalog_disabled_reason: summary.catalog_disabled_reason,
        catalog_load_error: summary.catalog_load_error,
        catalog_root: summary.catalog_root,
        app_studio_repo_root: summary.app_studio_repo_root,
    }
}

pub(crate) fn mask_sensitive(text: &str) -> String {
    let chars: Vec<char> = text.chars().collect();
    let mut output = String::with_capacity(text.len());
    let mut index = 0;
    while index < chars.len() {
        if chars[index] == 's'
            && chars.get(index + 1) == Some(&'k')
            && chars.get(index + 2) == Some(&'-')
        {
            let start = index;
            index += 3;
            while index < chars.len()
                && (chars[index].is_ascii_alphanumeric()
                    || chars[index] == '-'
                    || chars[index] == '_')
            {
                index += 1;
            }
            let token: String = chars[start..index].iter().collect();
            output.push_str(&crate::secret_store::mask_secret(&token));
        } else {
            output.push(chars[index]);
            index += 1;
        }
    }
    output
}

pub(crate) fn append_app_studio_gui_log(event: &str, attrs: &[(&str, String)]) {
    let log_dir = crate::setup::user_data_root()
        .join("data")
        .join("logs")
        .join("admin");
    if std::fs::create_dir_all(&log_dir).is_err() {
        return;
    }
    let path = log_dir.join("app_studio_gui.log");
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        use std::io::Write;
        let mut line = format!("{} {}", chrono::Local::now().to_rfc3339(), event);
        for (key, value) in attrs {
            if !value.trim().is_empty() {
                line.push(' ');
                line.push_str(key);
                line.push('=');
                line.push_str(&mask_sensitive(value));
            }
        }
        let _ = writeln!(file, "{line}");
    }
}

pub(crate) fn command_line_for_log(program: &Path, args: &[String]) -> String {
    let mut parts = vec![quote_log_arg(&program.display().to_string())];
    parts.extend(args.iter().map(|arg| quote_log_arg(arg)));
    parts.join(" ")
}

pub(crate) fn redact_cli_arg_value(args: &[String], key: &str) -> Vec<String> {
    let mut output = Vec::with_capacity(args.len());
    let mut redact_next = false;
    for arg in args {
        if redact_next {
            output.push("<redacted>".to_string());
            redact_next = false;
            continue;
        }
        output.push(arg.clone());
        if arg == key {
            redact_next = true;
        }
    }
    output
}

fn quote_log_arg(value: &str) -> String {
    if value.chars().any(|ch| ch.is_whitespace()) {
        format!("\"{}\"", value.replace('"', "\\\""))
    } else {
        value.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app_studio_result_reader::AppStudioResultSummary;
    use std::path::Path;

    #[test]
    fn secret_masking_hides_openai_key_like_tokens() {
        let masked = mask_sensitive("OPENAI_API_KEY=sk-test123456abcd done");

        assert!(masked.contains("sk-...abcd"));
        assert!(!masked.contains("test123456"));
    }

    #[test]
    fn secret_masking_does_not_over_redact_normal_text() {
        let text = "status=ok api_key_source=credential model=gpt-image-2";

        assert_eq!(mask_sensitive(text), text);
    }

    #[test]
    fn command_line_for_log_quotes_whitespace_and_redacts_selected_value() {
        let args = vec![
            "tools/app_studio/main.py".to_string(),
            "icon-regenerate".to_string(),
            "--user-revision-instruction".to_string(),
            "make icon simpler".to_string(),
        ];
        let redacted = redact_cli_arg_value(&args, "--user-revision-instruction");
        let rendered = command_line_for_log(
            Path::new("C:\\Program Files\\Python\\python.exe"),
            &redacted,
        );

        assert!(rendered.contains("\"C:\\Program Files\\Python\\python.exe\""));
        assert!(rendered.contains("--user-revision-instruction <redacted>"));
        assert!(!rendered.contains("make icon simpler"));
    }

    #[test]
    fn process_result_preserves_exit_stdout_stderr_and_summary_shape() {
        let summary = AppStudioResultSummary {
            app_id: Some("sample".to_string()),
            output_dir: Some("out".to_string()),
            execution_status: Some("warn".to_string()),
            approval_allowed: Some(true),
            ..Default::default()
        };

        let result = result_from_process(
            false,
            2,
            "stdout text".to_string(),
            "stderr text".to_string(),
            summary,
            Some(1.25),
            "ok",
        );

        assert!(!result.ok);
        assert_eq!(result.exit_code, 2);
        assert_eq!(result.stdout, "stdout text");
        assert_eq!(result.stderr, "stderr text");
        assert_eq!(result.app_id.as_deref(), Some("sample"));
        assert_eq!(result.output_dir.as_deref(), Some("out"));
        assert_eq!(result.execution_status.as_deref(), Some("warn"));
        assert_eq!(result.approval_allowed, Some(true));
        assert_eq!(result.timing_total_seconds, Some(1.25));
        assert_eq!(result.process_wall_clock_seconds, Some(1.25));
        assert!(result.user_message.contains("completed with warnings"));
    }
}
