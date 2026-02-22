export interface DishRecord {
  original_name: string;
  translated_name: string | null;
  description: string | null;
  ingredients: string[];
  price: string | null;
  image_url: string | null;
}

export interface MenuResult {
  job_id: string;
  status: 'processing' | 'completed' | 'partial' | 'failed';
  source_language: string | null;
  dishes: DishRecord[];
  error_message: string | null;
}
