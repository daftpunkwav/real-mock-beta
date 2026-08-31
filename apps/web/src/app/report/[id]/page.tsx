"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useReportLoad } from "@/features/report/useReportLoad";
import { normalizeScores } from "@/features/report/scoreFormat";
import { ScoreSummaryCard } from "@/features/report/components/ScoreSummaryCard";
import { ShortSessionAlert } from "@/features/report/components/ShortSessionAlert";
import { DimensionScores } from "@/features/report/components/DimensionScores";
import { ScoreRadar } from "@/features/report/components/ScoreRadar";
import { Section } from "@/features/report/components/Section";
import { FaceAnalysisCard } from "@/features/report/components/FaceAnalysisCard";
import { ActionLinks } from "@/features/report/components/ActionLinks";

export default function ReportPage() {
  const params = useParams();
  const sessionId = Number(params.id);
  const { report, duration, messagesCount, loading, error, retryGenerate } =
    useReportLoad(sessionId);

  if (loading) {
    return (
      <div className="page-shell-tight flex min-h-[40vh] items-center justify-center gap-2 text-[13px] text-ink-muted">
        <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
        生成报告中…
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="page-shell-tight py-16 text-center">
        <p className="mb-4 text-[13px] text-ink-muted">{error || "报告不可用"}</p>
        <div className="flex flex-wrap justify-center gap-2.5">
          {Number.isFinite(sessionId) && sessionId > 0 && (
            <button type="button" className="btn-secondary" onClick={retryGenerate}>
              <RefreshCw size={13} /> 生成 / 重新加载
            </button>
          )}
          <Link href="/interview" className="btn-primary">
            返回面试
          </Link>
        </div>
      </div>
    );
  }

  const scores = normalizeScores(report.score_breakdown);
  const shortSession =
    (typeof messagesCount === "number" && messagesCount < 6) ||
    (typeof duration === "number" && duration < 5);

  return (
    <div className="page-shell-tight anim-rise">
      <ScoreSummaryCard
        duration={duration}
        messagesCount={messagesCount}
        overallScore={report.overall_score}
      />

      <ShortSessionAlert show={shortSession} />

      <DimensionScores scores={scores} />
      <ScoreRadar scores={scores} />

      <Section title="优势" items={report.strengths} tone="success" />
      <Section title="不足" items={report.weaknesses} tone="danger" />
      <Section title="简历改进建议" items={report.resume_suggestions || []} tone="brand" />
      <Section title="面试表现建议" items={report.interview_suggestions || []} tone="brand" />
      <Section title="综合建议" items={report.improvement_suggestions} tone="brand" />
      <Section title="下一阶段训练计划" items={report.training_plan} tone="warning" />

      {report.presence_moments && report.presence_moments.length > 0 && (
        <Section title="临场关键时刻" items={report.presence_moments} tone="brand" />
      )}

      {report.face_analysis_summary && (
        <FaceAnalysisCard summary={report.face_analysis_summary} />
      )}

      <ActionLinks />
    </div>
  );
}
