# API documentation

Base path: `/api/v1`. In development, interactive documentation is at `/docs` and the schema at `/openapi.json`. Both are disabled by default in production.

The endpoint tables at the end of this file are generated from the running application by `scripts/generate_api_docs.py`.

## Authentication

Register or log in to receive a token, then send it on each request:

```text
Authorization: Bearer <access_token>
```

Tokens last 12 hours by default. Logging out or changing a password revokes all of the account's tokens.

## Conventions

| Topic | Behaviour |
|---|---|
| Lists | `{"items": [...], "total": 42, "page": 1, "page_size": 20}`. Use `page` and `page_size` |
| Timestamps | ISO 8601 in UTC |
| Coordinates | Pixels of the display image, `metadata.display_width` by `metadata.display_height` |
| Long-running work | Returns `202` with a job or comparison. Poll until finished |

## Errors

```json
{"detail": "Incorrect e-mail or password."}
```

Validation failures add field details and never echo submitted values:

```json
{"detail": "The submitted data is not valid.", "errors": [{"field": "password", "message": "String should have at least 10 characters"}]}
```

| Status | Meaning |
|---|---|
| 400 | The request was understood but refused, such as a wrong current password |
| 401 | Missing, invalid or revoked token |
| 404 | Not found, or belongs to another user. The two are deliberately indistinguishable |
| 409 | Conflicts with the current state, such as editing a project during processing |
| 413 | Too large, or too many files |
| 422 | Validation failed |
| 429 | Rate limited. See the `Retry-After` header |
| 500 | Internal error. Details are logged, never returned |
| 503 | `/health/ready` only: the database is unreachable |

## Example requests

Register:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/auth/register -H "Content-Type: application/json" -d '{"email":"you@example.com","full_name":"Your Name","password":"a-long-password"}'
```

```json
{"access_token": "<token>", "token_type": "bearer", "expires_in": 43200, "user": {"id": "...", "email": "you@example.com", "full_name": "Your Name", "created_at": "..."}}
```

Create a project (workspace IDs come from `GET /workspaces`):

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"workspace_id":"<id>","name":"Line 4 batch","category":"surface_material"}'
```

Upload images. Each file is accepted or rejected individually:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<id>/images -H "Authorization: Bearer $TOKEN" -F "files=@photo1.jpg" -F "files=@photo2.png"
```

```json
{"accepted": [{"id": "...", "filename": "photo1.jpg", "status": "uploaded", "metadata": {"file_format": "JPEG", "width": 1920, "height": 1080}}], "rejected": [{"filename": "photo2.png", "reason": "The file is corrupt or is not a valid image."}]}
```

Start the analysis, then poll the job:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<id>/analyze -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}'
```

```bash
curl http://127.0.0.1:8010/api/v1/jobs/<job-id> -H "Authorization: Bearer $TOKEN"
```

```json
{"id": "...", "status": "running", "items_total": 2, "items_done": 1, "stage": "Analysing photo2.png", "attempts": 1, "max_attempts": 2, "error_message": null}
```

Read the results:

```bash
curl http://127.0.0.1:8010/api/v1/images/<image-id>/results -H "Authorization: Bearer $TOKEN"
```

Record a review decision:

```bash
curl -X PATCH http://127.0.0.1:8010/api/v1/findings/<id>/review -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"decision":"false_positive","note":"Panel seam"}'
```

Compare two images:

```bash
curl -X POST http://127.0.0.1:8010/api/v1/comparisons -H "Authorization: Bearer $TOKEN" -F "workspace_id=<id>" -F "before=@a.jpg" -F "after=@b.jpg"
```

## Endpoints

<!-- ENDPOINTS -->

### Health

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/health` | Health | No | None | 200: JSON |
| `GET` | `/health/ready` | Ready | No | None | 200: JSON |

### Authentication

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Register | No | body: RegisterIn | 201: TokenOut |
| `POST` | `/api/v1/auth/login` | Login | No | body: LoginIn | 200: TokenOut |
| `POST` | `/api/v1/auth/logout` | Logout | Yes | None | 200: Message |

### Users

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/users/me` | Me | Yes | None | 200: UserOut |
| `PATCH` | `/api/v1/users/me` | Update Me | Yes | body: UserUpdate | 200: UserOut |
| `POST` | `/api/v1/users/me/password` | Change Password | Yes | body: PasswordChange | 200: TokenOut |
| `POST` | `/api/v1/users/me/delete` | Delete Account | Yes | body: AccountDelete | 200: Message |

### Workspaces

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/workspaces` | List Workspaces | Yes | None | 200: list of WorkspaceOut |
| `POST` | `/api/v1/workspaces` | Create Workspace | Yes | body: WorkspaceIn | 201: WorkspaceOut |
| `PATCH` | `/api/v1/workspaces/{workspace_id}` | Rename Workspace | Yes | body: WorkspaceIn | 200: WorkspaceOut |
| `DELETE` | `/api/v1/workspaces/{workspace_id}` | Delete Workspace | Yes | None | 204: none |

### Settings

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/settings` | Read Settings | Yes | None | 200: SettingsIn |
| `PUT` | `/api/v1/settings` | Write Settings | Yes | body: SettingsIn | 200: SettingsIn |

### Inspection projects

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/categories` | Categories | Yes | None | 200: JSON |
| `GET` | `/api/v1/projects` | List Projects | Yes | `workspace_id`, `q` (optional), `status` (optional), `category` (optional), `page` (optional), `page_size` (optional) | 200: Page of ProjectOut |
| `POST` | `/api/v1/projects` | Create Project | Yes | body: ProjectCreate | 201: ProjectOut |
| `GET` | `/api/v1/projects/{project_id}` | Get Project | Yes | None | 200: ProjectOut |
| `PATCH` | `/api/v1/projects/{project_id}` | Update Project | Yes | body: ProjectUpdate | 200: ProjectOut |
| `DELETE` | `/api/v1/projects/{project_id}` | Delete Project | Yes | None | 204: none |

### Images

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/images` | Upload Images | Yes | body: multipart form | 201: UploadResult |
| `GET` | `/api/v1/projects/{project_id}/images` | List Images | Yes | None | 200: list of ImageOut |
| `PATCH` | `/api/v1/images/{image_id}` | Update Image | Yes | body: ImageUpdate | 200: ImageOut |
| `DELETE` | `/api/v1/images/{image_id}` | Delete Image | Yes | None | 204: none |
| `GET` | `/api/v1/images/{image_id}/file` | Image File | Yes | `variant` (optional) | 200: binary file |

### Analysis

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/images/{image_id}/results` | Image Results | Yes | None | 200: ImageResults |
| `POST` | `/api/v1/projects/{project_id}/analyze` | Start Analysis | Yes | body: AnalyzeIn | 202: JobOut |
| `GET` | `/api/v1/jobs/{job_id}` | Get Job | Yes | None | 200: JobOut |
| `GET` | `/api/v1/projects/{project_id}/jobs` | Project Jobs | Yes | None | 200: list of JobOut |
| `POST` | `/api/v1/jobs/{job_id}/retry` | Retry Job | Yes | None | 202: JobOut |

### Findings

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/findings` | List Findings | Yes | `workspace_id`, `category` (optional), `review_status` (optional), `band` (optional), `finding_type` (optional), `project_id` (optional), `page` (optional), `page_size` (optional) | 200: Page of FindingOut |
| `GET` | `/api/v1/findings/{finding_id}` | Get Finding | Yes | None | 200: FindingDetail |
| `PATCH` | `/api/v1/findings/{finding_id}/review` | Review Finding | Yes | body: ReviewIn | 200: FindingDetail |

### Reports

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `POST` | `/api/v1/projects/{project_id}/reports` | Generate Report | Yes | body: ReportCreate | 201: ReportOut |
| `GET` | `/api/v1/reports` | List Reports | Yes | `workspace_id`, `project_id` (optional), `page` (optional), `page_size` (optional) | 200: Page of ReportOut |
| `GET` | `/api/v1/reports/{report_id}/file` | Report File | Yes | `download` (optional) | 200: binary file |
| `DELETE` | `/api/v1/reports/{report_id}` | Delete Report | Yes | None | 204: none |

### Image comparison

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `POST` | `/api/v1/comparisons` | Create Comparison | Yes | body: multipart form | 202: ComparisonOut |
| `GET` | `/api/v1/comparisons` | List Comparisons | Yes | `workspace_id`, `page` (optional), `page_size` (optional) | 200: Page of ComparisonOut |
| `GET` | `/api/v1/comparisons/{comparison_id}` | Get Comparison | Yes | None | 200: ComparisonOut |
| `DELETE` | `/api/v1/comparisons/{comparison_id}` | Delete Comparison | Yes | None | 204: none |
| `GET` | `/api/v1/comparisons/{comparison_id}/file` | Comparison File | Yes | `variant` | 200: binary file |

### Analytics

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/analytics/overview` | Overview | Yes | `workspace_id` | 200: JSON |
| `GET` | `/api/v1/analytics/insights` | Insights | Yes | `workspace_id`, `days` (optional) | 200: JSON |

### Model information

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/system/status` | System Status | Yes | None | 200: JSON |
| `GET` | `/api/v1/models` | Models | Yes | None | 200: JSON |

### AI assistant

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `GET` | `/api/v1/assistant/status` | Assistant Status | Yes | None | 200: AssistantStatus |
| `POST` | `/api/v1/assistant/conversations` | Create Conversation | Yes | body: ConversationCreate | 201: ConversationOut |
| `GET` | `/api/v1/assistant/conversations` | List Conversations | Yes | `project_id` (optional) | 200: list of ConversationOut |
| `GET` | `/api/v1/assistant/conversations/{conversation_id}` | Get Conversation | Yes | None | 200: ConversationOut |
| `POST` | `/api/v1/assistant/conversations/{conversation_id}/messages` | Post Message | Yes | `workspace_id` (optional), body: MessageIn | 201: MessageOut |

### Demo

| Method | Path | Purpose | Auth | Input | Success |
|---|---|---|---|---|---|
| `POST` | `/api/v1/demo` | Create Demo | Yes | None | 201: WorkspaceOut |
| `DELETE` | `/api/v1/demo` | Delete Demo | Yes | None | 200: Message |
