/** 录音/VAD/打断的全部魔数与正则。 */

/** 30 MB:长会话下录音 chunks 上限,超过时丢弃最早的 chunk 防止内存泄漏。 */
export const MAX_CHUNKS_BYTES = 30 * 1024 * 1024;
/** 静音触发最少需要累积的 chunk 数,防止首字节就被切。 */
export const MIN_CHUNKS_BEFORE_SILENCE = 2;
/** 默认静音时长：思考停顿不误切。 */
export const SILENCE_TRIGGER_MS = 1800;
/** 句末快提交：最近有 isFinal 且标点/interim 已空。 */
export const SILENCE_FAST_MS = 1000;
/** RMS 阈值,低于此视为静音。 */
export const SILENCE_RMS_THRESHOLD = 0.006;
/** 打断专用：更高能量，避免扬声器回声/环境噪音误打断。 */
export const BARGE_RMS_THRESHOLD = 0.028;
/** 连续高能量达到此时长才触发打断候选。 */
export const BARGE_SUSTAIN_MS = 700;
/** 至少约 1.2s 语音能量才允许静音提交（4096@16k ≈ 256ms/块）。 */
export const MIN_SPEECH_CHUNKS = 5;
/** 文本足够长时可放宽能量门槛。 */
export const MIN_TEXT_CHARS = 8;
/** interim 仍在更新时禁止提交。 */
export const INTERIM_ACTIVE_MS = 600;
/** final 后 interim 清空需稳定多久才可走快路径。 */
export const FINAL_SETTLE_MS = 400;
/** 语音活动回调节流（用于静音追问计时，不用于打断）。 */
export const SPEECH_ACTIVITY_THROTTLE_MS = 400;
export const TARGET_SAMPLE_RATE = 16000;
/** AI 期环形缓冲时长（秒），打断后作为下一轮采集起点。 */
export const RING_BUFFER_SEC = 2.5;
export const RING_BUFFER_MAX_BYTES = Math.floor(TARGET_SAMPLE_RATE * 2 * RING_BUFFER_SEC);

/** 开启发言采集前的短暂静默，避开扬声器余响。 */
export const CAPTURE_ARM_DELAY_MS = 450;
/** 打断后缩短武装延时（环缓已含触发语音）。 */
export const CAPTURE_ARM_AFTER_BARGE_MS = 200;

export const SENTENCE_END_RE = /[。！？.!?]$/;
