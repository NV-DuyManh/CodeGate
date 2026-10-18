# CodeGate — Báo cáo sửa lỗi và kiểm tra

**Ngày:** 18/10/2026 · **Nhánh tại máy:** `fix/codegate-runtime-ci-docs`<br>
**Commit xuất phát:** `30a0d1632aa313a9f202bc7c0fe7e4cb3dd1c4dd`<br>
**Phạm vi:** bản clone cục bộ của https://github.com/NV-DuyManh/CodeGate; bản sửa trên nhánh `fix/codegate-runtime-ci-docs`, chuẩn bị commit/push theo yêu cầu; chưa deploy.

## 1. Kết quả tổng hợp

| Kiểm tra | Kết quả đã quan sát |
|---|---|
| Backend CodeGate — toàn bộ `tests/codegate` | **231 passed, 6 skipped, 0 failed** |
| Frontend Vitest | **41 passed / 11 test files** |
| Frontend lint / build | Đạt; còn warning hooks/fast-refresh và bundle khoảng 819 kB trước gzip |
| Ruff `codegate tools` | Đạt; cấu hình cũ còn cảnh báo rule E999 đã bị loại bỏ |
| Bandit theo ngưỡng CI medium/high | Đạt, không có finding ở ngưỡng đó; low-severity không được coi là đã biến mất |
| Python installed-environment audit | Không tìm thấy advisory trong lần quét sau cập nhật |
| Npm audit | 0 vulnerability trong lần quét sau cập nhật |
| `pip check` | Không có dependency conflict |
| Compose config | Parse đạt; chưa chạy stack vì Docker daemon không sẵn sàng |
| Checker migration | Chấp nhận đúng head và từ chối head sai trên SQLite tạm; PostgreSQL chưa chạy |
| Upstream PR-Agent | **2578 passed, 0 failed, 2 skipped/xfailed** |

**Kết quả cuối:** hai nhóm lỗi upstream ở lượt trước đã xử lý; lượt tổng sau sửa không có bài thất bại. Hosted CI và các tích hợp ngoài vẫn cần kiểm tra riêng.

## 2. Các lỗi hành vi đã sửa

1. Nối StaticAnalysisRunner vào luồng phân tích chính trước scoring; không còn cần gọi runner thủ công để có bằng chứng static.
2. Chuẩn hóa đường dẫn finding, gắn changed-file và lọc metrics theo metadata PR để score đọc được bằng chứng phù hợp.
3. Khởi chạy analyzer bằng Python isolated mode `-I`, ngăn module trong repo giả mạo công cụ đã cài. Đã tái hiện bằng marker file an toàn trên cả 3 công cụ trước khi sửa.
4. Worker đồng bộ dùng event loop có vòng đời rõ ràng; sửa log terminal status khi SQLAlchemy trả String.
5. Mọi lệnh Git chuẩn bị static workspace có timeout; cleanup khi timeout/lỗi; token được redact khỏi stderr/log và không in exception argv.
6. Webhook dùng đúng biến cấu hình `GITHUB_WEBHOOK_SECRET`, thiếu secret trả 503, thiếu/sai chữ ký trả 401.
7. Session SQLite được chuẩn hóa UTC; bỏ bypass RBAC dựa trên `TESTING=1`.
8. Cấu hình/chạy test yêu cầu quyền quản lý; local executor cần opt-in phía server. Kiểm tra cả hai endpoint cấu hình và cấu hình local đã lưu trước đó.
9. PATCH test config commit dữ liệu; PUT ánh xạ các trường API sang cột JSON đúng.
10. Invitation xử lý UTC, email rỗng và status String đúng; thêm 12 regression cases.
11. Thư mục test phải resolve bên trong workspace được cấp cho cả executor local và Docker; không chỉ kiểm tra prefix `/tmp`.
12. Nonzero test exit không thể bị XML pass ghi đè; xóa artifact cũ; không chấp nhận coverage export lỗi.
13. Local pytest dùng đúng interpreter của môi trường backend, tránh alias `python` hỏng trên Windows.
14. Changed coverage chạy git diff trên checkout thực và chuẩn hóa đường dẫn khi chạy test trong thư mục con.
15. Output subprocess được drain liên tục và giữ tối đa khoảng 64 KiB mỗi stream; Docker container có tên riêng, resource/capability limits và cleanup.
16. Policy chỉ suy test pass từ execution COMPLETED + outcome PASSED; các trạng thái còn lại được warning/block theo yêu cầu policy.
17. OAuth redirect đọc frontend URL; cập nhật ví dụ env/Compose cho cấu hình mới và mounted key path.
18. Sửa 43 lỗi Ruff ở baseline bằng thay đổi cụ thể về import, tên chưa định nghĩa và định nghĩa trùng; không áp dụng formatter toàn repo.
19. CI không còn bỏ qua audit/secret scan/upstream test; PostgreSQL migration checker dùng cùng database và so sánh current heads với script heads.
20. Khai báo đủ analyzer runtime; cập nhật dependency có advisory; kiểm tra lại frontend watcher, build và test.
21. Sửa 3 test portability upstream: đọc UTF-8 rõ ràng và giả lập USERPROFILE cho `~` trên Windows; giữ nguyên các assertion kiểm tra hành vi.

## 3. Bằng chứng regression-first

| Nhóm | Trước sửa | Sau sửa và bằng chứng |
|---|---|---|
| Executor/report correctness | 7 regression failures | Đã qua lại trong bộ CodeGate tổng |
| Analyzer import isolation | 3 failures; shadow module thực sự tạo marker | 3 tests qua, công cụ thật chạy từ môi trường đã cài |
| Interpreter local | 1 failure gọi PATH `python` | Test qua khi dùng sys.executable |
| API security/config | 18 failed, 5 passed | 23 passed; bao gồm SQLite roundtrip và commit persistence |
| Invitations | UTC, email và status failures tái hiện riêng | 25 passed gồm 12 regressions và RBAC cũ |
| Static pipeline | Workspace failure bị báo completed; absolute path persistence | Git repo tại máy + Ruff/Bandit/Radon thật + score persistence qua |
| Git workspace | 3 failures (redaction/timeout/cleanup) | Các regression đã qua |
| Policy evidence | 18 failed trong tests mới | 31 passed gồm policy cũ và mới |
| Windows upstream fixtures | 3 failures trong lượt tổng trước sửa | 11 passed ở nhóm local provider/path expansion |

Một số tên scratch log đã được tái sử dụng trong lúc làm việc; số liệu bàn giao ưu tiên XML/log final đi kèm. Không dùng số test cũ như một benchmark hiệu năng.

## 4. Lệnh kiểm tra chính

Thực hiện từ thư mục CodeGate, PowerShell:

```powershell
$env:PYTHONPATH = '.'
.\.venv\Scripts\python.exe -m pytest tests/codegate -q -rs --tb=short
.\.venv\Scripts\python.exe -m pytest tests/unittest -q --tb=short
.\.venv\Scripts\python.exe -m ruff check codegate tools
.\.venv\Scripts\python.exe -m bandit -r codegate tools -ll -ii
.\.venv\Scripts\python.exe -m pip check
```

Frontend: `npm ci`, `npm run lint`, `npm run test:run`, `npm run build`, `npm audit`. Các bước này đã chạy sau dependency remediation. Generated `dashboard/src/tailwind.css` được phục hồi về bản tracked sau build để giữ diff tập trung; lệnh build sẽ sinh lại file.

Flake8 correctness subset `E9,F63,F7,F82` trên `codegate tools` đạt. Các file executor/regression mới của phần chạy test cũng được kiểm tra style với max line length 120. Không tuyên bố mọi file legacy đều đạt toàn bộ quy tắc style mặc định của Flake8; không tạo commit.

## 5. Sáu test được bỏ qua trong CodeGate

- 3 test đã đánh dấu skip sẵn do webhook pipeline refactoring (`test_github_sync_e2e`, `test_hardening_group04_3`).
- 2 test cần `POSTGRES_TEST_URL` (`test_postgres_tenant.py`).
- 1 test symlink escape cần quyền tạo symlink trên Windows; các case traversal khác chạy và đạt.

## 6. Hai nhóm lỗi upstream đã xử lý



- **Callback cleanup trên Windows:** asyncio có thể đánh thức timer sớm do độ phân giải đồng hồ. Cleanup giờ chờ theo deadline cố định, kiểm tra lại phần thời gian còn lại; worker vẫn được lịch chạy khi cửa sổ nhỏ của một vòng đã qua nhưng ngân sách toàn giai đoạn còn. Thêm test clock giả xác định để tái hiện early wakeup, giữ nguyên các test cancellation hiện có.
- **OpenRouter/LiteLLM contract:** model metadata hiện cho phép top-level reasoning_effort nên kỳ vọng luôn ném UnsupportedParamsError không còn đúng. Test giờ kiểm tra trực tiếp extra_body.reasoning cho effort và disabled reasoning. Adapter vẫn tạo explicit request body, không bỏ validation hay xfail.
- **Kiểm tra bổ sung:** sửa các optional import thiếu trong helper Pinecone/LanceDB và lỗi lint cơ học. Không cài thêm backend vector DB; chưa kiểm thử tích hợp vector DB thật.

Lượt upstream cuối: **2578 passed, 1 skipped, 1 xfailed, 0 failed**. Bộ CodeGate: **231 passed, 6 skipped, 0 failed**. Các warning deprecation vẫn tồn tại; hosted CI chưa được coi là thành công chỉ từ kết quả tại máy.

## 7. Dependency và kiểm tra bảo mật

- GitPython → **3.1.60**; PyJWT → **2.15.0**; pip của môi trường local → **26.2.1**.
- Runtime analyzer: Ruff **0.17.1**, Bandit **1.9.4**, Radon **6.0.1**.
- Frontend: scoped override `@tailwindcss/cli` → `@parcel/watcher 2.6.0`; lockfile cập nhật `source-map-js` và `undici` tương thích. Đã thử watcher build ban đầu và rebuild sau thay đổi file.
- Python audit dùng môi trường audit riêng để quét `.venv/Lib/site-packages`, gồm các package thực sự đã cài. Log/JSON `codegate-pip-audit-verified` là kết quả cuối; các file `*-final` cũ của lần baseline không được dùng làm kết quả bàn giao.
- npm audit cuối báo 0 vulnerabilities. Bandit ngưỡng CI medium/high báo 0 findings. Đây là trạng thái scanner tại thời điểm chạy, không thay thế kiểm toán bảo mật đầy đủ.
- Có test ký/xác minh JWT RS256 thật cho GitHub App sau nâng PyJWT.

## 8. Chưa xác minh hoặc còn giới hạn

- Chưa chạy PostgreSQL/Redis/Celery/GitHub/AI end-to-end thật và chưa build/chạy Docker images trong đợt này. Docker daemon không sẵn sàng; Compose syntax validation đã qua.
- Checker migration đã chạy trên SQLite tạm để kiểm tra đúng/sai head, chưa kiểm tra PostgreSQL migration thực.
- Local executor chỉ cho repo tin cậy, không phải sandbox. Docker socket + đường dẫn workspace trong worker container cần được xác minh deployment trước khi chạy mã không tin cậy.
- Callback installation chưa chứng minh quyền user với installation; PR-Agent settings dùng chung cần đánh giá concurrency/multi-tenant.
- Token static clone vẫn có thể hiện tạm ở argv/`.git/config`; test service clone private repo chưa có luồng token tương ứng.
- AI adapter lỗi có thể chặn static; retry sau partial commits chưa được thiết kế lại để tự phục hồi idempotent toàn bộ.
- Quality completeness/maintainability và reviewer history có giới hạn nêu trong handbook.
- Frontend còn lint warnings và cảnh báo bundle lớn. Các warning deprecation backend còn tồn tại.
- Chưa chạy gitleaks action hosted tại máy; CI giữ secret scan bắt buộc.

## 9. Sử dụng bản bàn giao

- Giải nén `CodeGate_Fixed.zip` vào thư mục mới; xem `README.md`, handbook và báo cáo này.
- ZIP chứa source; không kèm launcher `.exe`/`.dll` dựng sẵn từ repo vì chưa rebuild/kiểm chứng binary. Dùng source launcher nếu cần.
- Cài dependencies theo handbook; không sao chép `.venv`/`node_modules` giữa máy.
- `CodeGate_Fixes.patch` áp dụng từ commit xuất phát bằng `git apply`; bản ZIP đã chứa các thay đổi, không apply patch thêm lần nữa vào ZIP.
- `validation/` trong ZIP chứa bằng chứng được chọn. `SOURCE_MANIFEST.json` ghi SHA-256 file nguồn để kiểm tra archive.
- Nhánh GitHub của bản sửa: https://github.com/NV-DuyManh/CodeGate/tree/fix/codegate-runtime-ci-docs. Xem lịch sử commit và pull request để kiểm tra trạng thái upload/CI; bản báo cáo được chốt trước bước push.
