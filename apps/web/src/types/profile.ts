/** 用户档案 / 简历 / 企业信息 / 选项类型。 */

export interface UserProfile {
  id: number;
  name: string;
  gender?: string;
  identity?: string;
  school?: string;
  major?: string;
  graduation_year?: string;
  job_direction: string;
  experience_years: string;
  work_years_detail?: string;
  current_company?: string;
  expected_salary?: string;
  self_intro?: string;
  tech_domains: string[];
  target_role: string;
  github_username?: string;
  portfolio_url?: string;
  linkedin_url?: string;
  city?: string;
  preferred_languages?: string;
  career_highlights?: string;
  open_to_remote?: string;
  notice_period?: string;
  education_level?: string;
  expected_city?: string;
  email?: string;
  phone?: string;
  certificates?: string;
  english_level?: string;
  signature_projects?: string;
  strengths?: string;
  weaknesses?: string;
  updated_at?: string;
}

export interface CandidateProfile {
  name: string;
  education: Record<string, string>[];
  work_experience: Record<string, string>[];
  skills: string[];
  projects: Record<string, string>[];
  summary: string;
}

export interface DimensionScore {
  score: number;
  comment?: string;
}

export interface RewriteExample {
  before: string;
  after: string;
}

export interface ResumeAnalysis {
  score: number;
  strengths: string[];
  weaknesses: string[];
  improvement_suggestions: string[];
  predicted_questions: string[];
  dimension_scores?: Record<string, DimensionScore | number>;
  ats_keywords?: string[];
  missing_keywords?: string[];
  project_deep_dive?: string[];
  red_flags?: string[];
  role_fit_summary?: string;
  seniority_estimate?: string;
  rewrite_examples?: Array<string | RewriteExample>;
  interview_risk_areas?: string[];
  overall_narrative?: string;
  layout_review?: string;
  typography_review?: string;
  content_review?: string;
  market_insights?: string[];
  search_queries_used?: string[];
  /** 生动化扩展(旧评价数据可空缺,前端按空缺降级) */
  headline?: string;
  first_impression?: string;
  interviewer_comments?: string[];
  benchmark_percentile?: number | null;
}

export interface ResumePickerItem {
  id: number;
  filename: string;
  is_active?: boolean;
  score?: number | null;
}

export interface Resume {
  id: number;
  filename: string;
  file_type: string;
  parsed_profile: CandidateProfile;
  is_active?: boolean;
  score?: number | null;
  analysis?: ResumeAnalysis | Record<string, unknown>;
  created_at: string;
}

export interface CompanyInfo {
  id: string;
  name: string;
  style: string;
  focus_areas: string[];
  sample_questions: string[];
}

export interface Options {
  roles: string[];
  levels: string[];
  experience_years: string[];
  companies: CompanyInfo[];
  personalities: { id: string; name: string; description: string }[];
  interview_styles: { id: string; name: string; description: string }[];
  workflow_types: { id: string; name: string; phases: string[] }[];
  phase_labels?: Record<string, string>;
  avatars?: { id: string; name: string; voice?: string }[];
  scenes?: { id: string; name: string }[];
  tts_voices?: { id: string; name: string }[];
  silence_nudge_seconds?: number;
}

export type InterviewStyleId = "guided" | "deep_dive" | "continuous" | "challenging";

export interface ResumeActivateResponse {
  id: number;
  is_active: boolean;
}

export interface PrepSessionCreateResponse {
  id: number;
  access_token?: string | null;
}

export interface PrepMessageResponse {
  reply: string;
  token_usage: number;
}
