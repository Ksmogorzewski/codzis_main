import { useEffect, useState } from "react";

// Routing po hashu (#/sciezka?param=1): S3 + CloudFront nie potrzebują wtedy reguł dla głębokich linków
export type Route = { path: string; params: URLSearchParams };

export function parseHash(hash: string = window.location.hash): Route {
  const [path = "", query = ""] = hash.replace(/^#\/?/, "").split("?");
  return { path, params: new URLSearchParams(query) };
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash());
  useEffect(() => {
    const onChange = () => setRoute(parseHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string) {
  window.location.hash = `#/${path}`;
}

// Zmiana adresu bez wywołania hashchange (np. usunięcie ?status=... po pokazaniu komunikatu)
export function replaceHash(path: string) {
  history.replaceState(null, "", `${window.location.pathname}${window.location.search}#/${path}`);
}
