import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import fc from 'fast-check';
import DishCard from './DishCard';
import type { DishRecord } from './types';

const dishRecordArb: fc.Arbitrary<DishRecord> = fc.record({
  original_name: fc.string({ minLength: 1, maxLength: 50 }),
  translated_name: fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: null }),
  description: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null }),
  ingredients: fc.array(fc.string({ minLength: 1, maxLength: 30 }), { maxLength: 5 }),
  price: fc.option(fc.string({ minLength: 1, maxLength: 15 }), { nil: null }),
  image_url: fc.option(fc.webUrl(), { nil: null }),
});

/**
 * Feature: menu-vision
 * Property 6: Card rendering displays exactly non-null fields
 * Validates: Requirements 5.1, 5.3
 */
describe('Property 6: Card rendering displays exactly non-null fields', () => {
  it('renders all non-null fields and omits null fields', () => {
    fc.assert(
      fc.property(dishRecordArb, (dish) => {
        const { container } = render(<DishCard dish={dish} />);
        const text = container.textContent ?? '';

        // original_name is always present
        expect(text).toContain(dish.original_name);

        // translated_name
        if (dish.translated_name) {
          expect(text).toContain(dish.translated_name);
        }

        // description
        if (dish.description) {
          expect(text).toContain(dish.description);
        }

        // ingredients
        for (const ing of dish.ingredients) {
          expect(text).toContain(ing);
        }

        // price
        if (dish.price) {
          expect(text).toContain(dish.price);
        }

        // image
        const img = container.querySelector('img');
        if (dish.image_url) {
          expect(img).not.toBeNull();
          expect(img?.getAttribute('src')).toBe(dish.image_url);
        } else {
          expect(img).toBeNull();
        }
      }),
      { numRuns: 100 },
    );
  });
});
