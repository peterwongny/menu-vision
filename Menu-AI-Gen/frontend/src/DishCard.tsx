import type { DishRecord } from './types';

interface DishCardProps {
  dish: DishRecord;
}

export default function DishCard({ dish }: DishCardProps) {
  return (
    <article className="dish-card">
      {dish.image_url && (
        <img src={dish.image_url} alt={dish.original_name} loading="lazy" />
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
