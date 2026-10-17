// Wynik funkcji, która może się nie udać: albo dane, albo błąd (bez wyjątków między warstwami).
export type Result<T, E> = { data: T; error: null } | { data: null; error: E };

export const ok = <T>(data: T): { data: T; error: null } => ({ data, error: null });
export const err = <E>(error: E): { data: null; error: E } => ({ data: null, error });
