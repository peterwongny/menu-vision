import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import { validateFile } from './validation';

const SUPPORTED_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const MAX_SIZE = 10 * 1024 * 1024;

/**
 * Feature: menu-vision
 * Property 1: File format validation accepts only supported types
 * Validates: Requirements 1.2, 1.3, 1.5
 */
describe('Property 1: File format validation', () => {
  it('accepts supported types under 10 MB', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...SUPPORTED_TYPES),
        fc.integer({ min: 1, max: MAX_SIZE }),
        (type, size) => {
          const result = validateFile({ type, size });
          expect(result.valid).toBe(true);
          expect(result.error).toBeUndefined();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects unsupported MIME types', () => {
    const unsupportedType = fc.string({ minLength: 1 }).filter(
      (t) => !SUPPORTED_TYPES.includes(t),
    );

    fc.assert(
      fc.property(
        unsupportedType,
        fc.integer({ min: 1, max: MAX_SIZE }),
        (type, size) => {
          const result = validateFile({ type, size });
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('rejects files exceeding 10 MB', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...SUPPORTED_TYPES),
        fc.integer({ min: MAX_SIZE + 1, max: MAX_SIZE * 5 }),
        (type, size) => {
          const result = validateFile({ type, size });
          expect(result.valid).toBe(false);
          expect(result.error).toBeDefined();
        },
      ),
      { numRuns: 100 },
    );
  });

  it('accepts if and only if type is supported AND size <= 10 MB', () => {
    const anyType = fc.oneof(
      fc.constantFrom(...SUPPORTED_TYPES),
      fc.string({ minLength: 1 }),
    );
    const anySize = fc.integer({ min: 0, max: MAX_SIZE * 5 });

    fc.assert(
      fc.property(anyType, anySize, (type, size) => {
        const result = validateFile({ type, size });
        const shouldBeValid = SUPPORTED_TYPES.includes(type) && size <= MAX_SIZE;
        expect(result.valid).toBe(shouldBeValid);
      }),
      { numRuns: 200 },
    );
  });
});
