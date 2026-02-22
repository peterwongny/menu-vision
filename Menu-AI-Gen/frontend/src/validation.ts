const SUPPORTED_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const MAX_SIZE_BYTES = 10 * 1024 * 1024; // 10 MB

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

export function validateFile(file: { type: string; size: number }): ValidationResult {
  if (!SUPPORTED_TYPES.has(file.type)) {
    return {
      valid: false,
      error: `Unsupported file format. Please use JPEG, PNG, or WEBP.`,
    };
  }
  if (file.size > MAX_SIZE_BYTES) {
    return {
      valid: false,
      error: `File exceeds the maximum size of 10 MB.`,
    };
  }
  return { valid: true };
}
