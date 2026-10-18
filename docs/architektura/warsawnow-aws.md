# WarsawNow — architektura AWS

Diagram: `warsawnow-aws.drawio` (draw.io, ikony `mxgraph.aws4`; import do Lucidchart: *File → Import → draw.io*). Region: `eu-central-1`. Źródło prawdy: `infra/*.tf` i `AGENTS.md`.

## Przepływy

**Portal klienta (`portal.waw-out.pl`)**
1. Przeglądarka pobiera front React z CloudFront → S3 (OAC).
2. Logowanie: Cognito, pula klientów (Hosted UI + PKCE), opcjonalnie Google OAuth (sekret `codzis/google-oauth`).
3. Wywołania API idą do API Gateway HTTP API z tokenem JWT; Cognito weryfikuje go, zanim uruchomi się Lambda.
4. `/api/*` → Lambda `client-api`: profil, zapisy, ekipy, znajomi (DynamoDB `users`, `attendance`, `event-stats`, `crews`, `friends`), Eksploruj czyta `codzis-events` scanem z pamięcią 5 min.
5. `/api/recommendations` → Lambda rekomendera (obraz z ECR, model mpnet): indeks w S3 `data`, rekordy z `codzis-events`, zapisane zestawy w `codzis-recommendations`, ranking DeepSeek tylko w fazie 2 (w tle).

**Panel partnera (`partner.waw-out.pl`)**
6. CloudFront serwuje panel z S3, zdjęcia z S3 `photos` (`/photos/*`) i przekazuje `/api/*` do API Gateway REST.
7. REST API sprawdza klucz API albo ID token z puli partnerów Cognito; Lambda API partnera zapisuje `submissions`, `partners`, `payments` i wysyła ogłoszenia do SQS.

**Zasilanie danymi**
8. Importer (ECS Fargate) pobiera dane z API UM i wysyła rekordy schematu v1 do SQS. API UM blokuje IP AWS, więc dziś import idzie z laptopa (`scripts/import-local.sh`).
9. EventBridge co minutę (`worker_check_minutes`) wywołuje Lambdę dispatcher, która uruchamia taggera (`RunTask`), gdy w kolejce są wiadomości.
10. Tagger (ECS Fargate Spot) taguje wydarzenia przez DeepSeek, zapisuje zdjęcia w standardzie do S3 `photos` i rekordy do `codzis-events`.

## Usługi

| Usługa | Rola |
|---|---|
| CloudFront ×2 | portal klienta, panel partnera (+ zdjęcia, proxy REST API) |
| S3 | front klienta, panel partnera, `photos`, `data` (indeks rekomendera, surowe dane) |
| Cognito ×2 | pule klientów i partnerów, logowanie Google |
| API Gateway | HTTP API (JWT) dla klienta, REST API (klucz / ID token) dla partnera |
| Lambda | `client-api`, rekomender (kontener), API partnera, dispatcher |
| DynamoDB | `codzis-events`, dane użytkowników, `codzis-recommendations`, tabele partnera |
| SQS | kolejka wydarzeń + DLQ |
| ECS Fargate | importer, tagger |
| EventBridge | harmonogramy: dispatcher, importer, rozgrzewanie i odświeżanie rekomendera |
| SSM / Secrets Manager | klucze DeepSeek i API UM / klient OAuth Google |
| ECR, CloudWatch Logs | obrazy kontenerów, logi JSON Powertools |

## Decyzje

- Serverless (Lambda + DynamoDB `PAY_PER_REQUEST`), ECS tylko dla długich zadań wsadowych.
- Każda tabela ma jednego zapisującego; bez `scan` w ścieżce żądania poza świadomym wyjątkiem Eksploruj (cache 5 min).
- LLM nigdy w ścieżce GET: rekomendacje liczą się w tle i są zapisywane per użytkownik.
- Na diagramie pominięto IAM, ACM, Route 53 / DNS, VPC i podsieci (taski ECS działają w publicznych podsieciach).
