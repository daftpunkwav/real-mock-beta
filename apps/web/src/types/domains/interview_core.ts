/** 面试核心域：配置 / 会话 / 报告 / 成长 / 多模态输入。 */

import type { InterviewStyleId } from "./profile";

export interface InterviewConfig {
  role: string;
  level: string;
  company: string;
  workflow_type: string;
  personality: string;
  strictness: number;
  interview_style: InterviewStyleId;
  resume_id?: number | null;
  avatar_id?: string;
  scene_id?: string;
}

export interface InterviewSession {
  id: number;
  role: string;
  level: string;
  company: string;
  workflow_type: string;
  personality: string;
  strictness: number;
  interview_style: string;
  avatar_id?: string;
  scene_id?: string;
  status: string;
  current_phase: string;
  overall_score?: number;
  started_at?: string;
  ended_at?: string;
  created_at: string;
  access_token?: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp?: string;
}

export interface ScoreBreakdown {
  technical: number;
  communication: number;
  project_depth: number;
  problem_solving: number;
  presence?: number;
  politeness?: number;
  overall: number;
}

export interface InterviewReport {
  overall_score: number;
  score_breakdown: ScoreBreakdown;
  strengths: string[];
  weaknesses: string[];
  improvement_suggestions: string[];
  resume_suggestions?: string[];
  interview_suggestions?: string[];
  training_plan: string[];
  phase_summary: Record<string, string>;
  face_analysis_summary: string;
  presence_moments?: string[];
}

export interface GrowthRecord {
  id: number;
  session_id: number;
  weak_skills: string[];
  training_plan: string[];
  created_at: string;
}

/** 多模态输入 */
export interface FaceAnalysis {
  dominant_emotion?: string;
  emotion_scores?: Record<string, string>;
  eye_contact?: boolean;
  smile?: boolean;
  confidence?: number;
  timestamp_ms?: number;
  [extra: string]: unknown;
}
