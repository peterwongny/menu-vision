import type { DishRecord } from './types';

interface DishCardProps {
  dish: DishRecord;
}

export default function DishCard({ dish }: DishCardProps) {
  const hasImage = dish.image_url && dish.image_url !== 'placeholder://no-image';

  return (
    <article className="dish-card">
      {hasImage ? (
        <img src={dish.image_url!} alt={dish.original_name} loading="lazy" />
      ) : (
        <div className="dish-image-placeholder" aria-label="Image loading">
          <div className="spinner spinner-small" />
        </div>
      )}
      <div className="dish-card-body">
        <h3>{dish.original_name}</h3>
        {dish.translated_name && (
          <p className="dish-translated">{dish.translated_name}</p>
        )}
        {dish.description && (
          <p className="dish-description">{dish.description}</p>
        )}
        {dish.ingredients.length > 0 && (
          <p className="dish-ingredients">{dish.ingredients.join(', ')}</p>
        )}
        {dish.price && (
          <p className="dish-price">{dish.price}</p>
        )}
      </div>
    </article>
  );
}
