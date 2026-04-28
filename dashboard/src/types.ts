export interface GameItem {
  title: string;
  link: string;
  end_date: string;
  description: string;
  thumbnail: string;
  store: string;
  /** 'game' (default) or 'dlc' */
  game_type?: string;
  /** Original retail price before the free promotion (e.g. "$19.99") */
  original_price?: string;
  /** Review scores from all available sources (Steam user labels, Metascore strings) */
  review_scores?: string[];
}

export interface GamesHistoryResponse {
  games: GameItem[];
  total: number;
  limit: number;
  offset: number;
}

export type SortField = 'title' | 'end_date';
export type SortDirection = 'asc' | 'desc';

/** Server-side store filter */
export type StoreFilter = 'all' | 'epic' | 'steam';

/** Server-side promotion-status filter */
export type StatusFilter = 'all' | 'active' | 'expired';
