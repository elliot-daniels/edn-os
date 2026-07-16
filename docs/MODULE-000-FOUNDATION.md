# Module 000 — Foundation

> **Knowledge Compounds.**

**MOD-000** · Foundation is the smallest shared platform layer required by all durable EDN OS modules. It exists to prevent duplication of common concerns across Memory, Business, Home, Intelligence, and future modules — without becoming a dumping ground or delaying feature delivery.

Implementation is delivered through short development sprints. Sprints schedule work; they do not define architecture.

---

## Purpose

Provide typed, testable platform primitives that every module can depend on:

- configuration and data-root policy;
- logging;
- shared error hierarchy;
- versioning conventions;
- cross-module types;
- minimal extension contracts;
- common utilities genuinely reused by multiple modules.

Foundation must be implemented before Module 001 (Memory).

---

## Why Foundation Exists

Without Foundation, each module would independently implement configuration loading, log setup, path validation, version metadata, and file fingerprinting — creating drift and duplicated bugs.

Foundation centralises **platform governance only**. Feature logic, domain models, and storage schemas remain in their owning modules.

---

## Permanent Scope

Foundation may define **only** these capabilities:

| # | Capability | Detail |
|---|------------|--------|
| 1 | **Configuration** | Typed application settings; production data-root configuration; safe example config in Git; real local config excluded from Git; validation with clear errors |
| 2 | **Logging** | Common logging setup; human-readable operational logs; no sensitive record content; modules request loggers — they do not configure logging independently |
| 3 | **Shared errors** | Small hierarchy: configuration, validation, storage, security, external dependency; domain-specific errors stay in owning modules |
| 4 | **Platform versioning** | Application version; schema-version conventions; module-version conventions; semantic versioning guidance |
| 5 | **Shared platform types** | Identifiers, timestamps, result/status types, `SensitivityStatus` — only where genuinely cross-module |
| 6 | **Security and path policy** | Approved data-root concept; production default `E:\EDN OS`; code outside data root; Git holds code and docs only; no runtime encryption verification in initial implementation |
| 7 | **Extension contracts** | Minimal concept for future connectors/adapters — not a plugin framework, service locator, DI container, event bus, or dynamic registry |
| 8 | **Common utilities** | Utilities demonstrably needed by multiple modules; SHA-256 file fingerprinting is owned here |

---

## Explicit Exclusions

Foundation must **not** include:

- PST parsing, email models, SQLite business schemas, search, FTS5, AI
- GUI or web interfaces
- Home Assistant, Microsoft 365, CRM, project management, finance
- Workflow automation, event bus, plugin marketplace
- Dependency-injection framework, secrets vault
- User authentication, multi-user permissions
- Network services, cloud deployment

If a concern is used by only one module, it stays in that module.

---

## Responsibilities

| Area | Foundation owns | Modules own |
|------|-----------------|-------------|
| Config | Load, validate, expose settings | Module-specific settings keys and defaults |
| Logging | Logger factory, format, handlers | Log messages and context |
| Errors | Platform base exceptions | Domain exceptions extending or wrapping platform errors |
| Versioning | App version, version conventions | Module version constants, schema versions for module DBs |
| Types | `RecordId`, `Timestamp`, `ResultStatus`, `SensitivityStatus` | Message, attachment, CRM record, etc. |
| Paths | Data-root policy and validation | Module-specific subpaths under data root |
| Fingerprinting | SHA-256 file hash utility | When and what to fingerprint |
| Extensions | Minimal `Connector` protocol concept | Concrete adapters (PST, M365, etc.) |

---

## Contracts

### Configuration

```
Settings.load(config_path) -> Settings
Settings.validate() -> None  # raises ConfigurationError
Settings.data_root -> Path
```

- Example configuration committed to Git (e.g. `config/settings.example.toml`).
- Real configuration at `E:\EDN OS\Configuration\` — excluded from Git.

### Logging

```
get_logger(name: str) -> Logger
```

Modules call `get_logger(__name__)`. Foundation configures handlers, format, and log directory once at startup.

### Shared errors

```
EdnOsError
├── ConfigurationError
├── ValidationError
├── StorageError
├── SecurityError
└── ExternalDependencyError
```

Module domain errors (e.g. `ImportError`, `ExtractionError`) live in the owning module and may wrap platform errors.

### Extension contract (minimal)

```
Connector  # protocol — name and capability metadata only
```

No plugin registry, dynamic loading, or service locator in Module 000.

### File fingerprinting

```
fingerprint_file(path: Path) -> str  # SHA-256 hex
```

---

## Configuration Policy

| Item | Rule |
|------|------|
| Production data root | `E:\EDN OS` (configurable) |
| Example config | Safe defaults; committed to Git |
| Local config | Real paths and overrides; never committed |
| Validation | Fail fast with `ConfigurationError` and clear message |
| Test override | Temporary directories permitted in unit tests |

---

## Logging Policy

| Item | Rule |
|------|------|
| Location | `E:\EDN OS\Logs\` in production |
| Format | Human-readable; timestamp, level, module, message |
| Sensitive content | No message bodies, attachment content, or credentials |
| Setup | Foundation configures once; modules request loggers |

---

## Error Ownership

| Layer | Examples |
|-------|----------|
| Foundation | `ConfigurationError`, `ValidationError`, `StorageError` |
| Memory | `ExtractionError`, `ImportRunError`, `SearchQueryError` |
| Future modules | Own domain errors; may inherit from `EdnOsError` |

---

## Versioning Policy

| Concept | Convention |
|---------|------------|
| Module IDs | `MOD-000` Foundation, `MOD-001` Memory, etc. |
| Application version | Semantic versioning (`MAJOR.MINOR.PATCH`) |
| Module version | Each module declares `MODULE_VERSION` independently |
| Schema version | `{module_id}.schema_version` integer; incremented when module DB schema changes |
| ADRs | Reserved as `ADR-NNN`; create only when a significant architectural decision requires one |

Do not invent database migrations before a module defines a schema. Memory schema versioning is declared by Memory; Foundation provides the convention only.

---

## Testing Requirements

| Requirement | Detail |
|-------------|--------|
| Unit tests | Configuration validation, logger factory, fingerprint utility, error hierarchy |
| Isolation | No dependency on Memory or other feature modules |
| Directories | Temporary local paths; no production data root required in CI |
| Coverage | Every public Foundation API has at least one test |

---

## Initial Implementation Artefacts

| # | Item |
|---|------|
| 1 | `src/edn/foundation/` package per `ARCHITECTURE.md` |
| 2 | `config/settings.example.toml` (safe example; committed) |
| 3 | Platform error hierarchy |
| 4 | Logger factory and setup |
| 5 | Settings loader with validation |
| 6 | `fingerprint_file` utility |
| 7 | Shared platform types |
| 8 | Version metadata (`__version__`, conventions documented) |
| 9 | Tests under `tests/foundation/` |
| 10 | `.gitignore` entries for local configuration |

---

## Initial Implementation Complete

- [ ] Settings load, validate, and expose data root
- [ ] Example configuration committed; local configuration excluded from Git
- [ ] Logger factory configured; modules receive loggers without self-configuration
- [ ] Platform error hierarchy defined and tested
- [ ] Application and module version conventions documented in code
- [ ] `SensitivityStatus` and shared types available
- [ ] Data-root policy enforced via configuration validation
- [ ] `fingerprint_file` utility tested
- [ ] Minimal `Connector` protocol defined (no registry)
- [ ] Unit tests pass in CI with temporary directories
- [ ] Foundation imports no feature module

---

## Risks and Safeguards

| Risk | Safeguard |
|------|-----------|
| Foundation becomes a dumping ground | Constitution principle: shared code only when ≥2 modules need it or essential governance |
| Foundation delays Memory | Keep scope to eight defined capabilities; no speculative infrastructure |
| Over-abstraction | No DI container, event bus, or plugin framework |
| Leaking feature concerns | Code review against explicit exclusions list |
| Configuration drift | Single settings loader; example config in Git |

---

## Dependencies

- Python (version to be pinned during initial implementation)
- Standard library only for Module 000 initial implementation (no external packages unless justified)

---

© EDN Systems
