# TAFM Assistance — Documentation Index

This folder contains comprehensive documentation for the TAFM Assistance AI Trading Agent project.

---

## 📚 Available Documentation

### Feature Documentation

| File | Description | Status |
|------|-------------|--------|
| [HISTORICAL_DATA_PAGE.md](HISTORICAL_DATA_PAGE.md) | Complete guide to the Historical Data page with 22-column analysis table | ✅ Current |
| [HISTORICAL_DATA_CHANGES.md](HISTORICAL_DATA_CHANGES.md) | Change summary and implementation details for Historical Data page | ✅ Current |

---

## 🛠️ Instruction Files

Located in `.github/instructions/`:

| File | Purpose | Applies To |
|------|---------|------------|
| `python-backend.instructions.md` | Backend Python code conventions (LangGraph, FastAPI, Kite Connect) | `trading_bot/**/*.py` |
| `react-ui.instructions.md` | React UI conventions (design system, components, hooks, state) | `trading_ui/src/**/*.{jsx,js,css}` |
| `trading-domain.instructions.md` | Trading rules (R:R gates, scenario gates, strategies, indicators) | `trading_bot/**` |
| `database.instructions.md` | Database schema, TimescaleDB, SQL migrations | `trading_bot/scripts/*.sql` |
| `llm-training.instructions.md` | LLM training pipeline (dataset, fine-tuning, Modelfile) | `llm_training/**` |

---

## 📖 Project Overview

Located at `.github/copilot-instructions.md`:
- Architecture overview (5 components)
- Build & run commands
- Critical gotchas
- System capabilities (analysis-only mode)
- Non-negotiable trading rules
- Key files reference
- Agent & prompt inventory

---

## 🔍 Quick Links by Topic

### Historical Data Page
- **Full Feature Docs**: [HISTORICAL_DATA_PAGE.md](HISTORICAL_DATA_PAGE.md)
- **Change Summary**: [HISTORICAL_DATA_CHANGES.md](HISTORICAL_DATA_CHANGES.md)
- **UI Instructions**: `../.github/instructions/react-ui.instructions.md` (Historical Data Page section)
- **Project Overview**: `../.github/copilot-instructions.md` (UI Architecture → Historical Data Page)

### Trading Strategies
- **Domain Rules**: `../.github/instructions/trading-domain.instructions.md`
- **Backend Implementation**: `../.github/instructions/python-backend.instructions.md`
- **Technical Indicators**: See Historical Data Page docs for client-side calculations

### UI Development
- **React Conventions**: `../.github/instructions/react-ui.instructions.md`
- **Design System**: See project overview for design tokens and theme CSS
- **Component Structure**: See React UI instructions for folder layout

### Backend Development
- **Python Conventions**: `../.github/instructions/python-backend.instructions.md`
- **API Endpoints**: See Python backend instructions for FastAPI patterns
- **Database**: `../.github/instructions/database.instructions.md`

### LLM Training
- **Training Pipeline**: `../.github/instructions/llm-training.instructions.md`
- **Modelfile**: `../../llm_training/Modelfile`
- **Output Contract**: See project overview for JSON format

---

## 📝 Documentation Standards

### When to Create New Documentation
- **New UI Page**: Create feature doc in `.github/docs/` + update `react-ui.instructions.md`
- **New Trading Strategy**: Update `trading-domain.instructions.md` + `python-backend.instructions.md`
- **New Backend Module**: Update `python-backend.instructions.md`
- **New Database Table**: Update `database.instructions.md`

### File Naming Convention
- Feature docs: `{FEATURE_NAME}_PAGE.md` or `{FEATURE_NAME}_COMPONENT.md`
- Change summaries: `{FEATURE_NAME}_CHANGES.md`
- Keep README-style index files as `README.md` in subfolders

### Required Sections in Feature Docs
1. **Overview** — Purpose, location, status
2. **Features** — What it does
3. **Technical Details** — How it works (algorithms, formulas, logic)
4. **CSS/Styling** — Visual patterns and classes
5. **API Integration** — Backend dependencies
6. **Testing** — Checklist of validated scenarios
7. **Known Limitations** — What doesn't work yet
8. **Future Enhancements** — Planned improvements
9. **Related Files** — Source code references

---

## 🚀 Getting Started

1. **For new contributors**: Start with `../.github/copilot-instructions.md` for project overview
2. **For UI work**: Read `../.github/instructions/react-ui.instructions.md`
3. **For backend work**: Read `../.github/instructions/python-backend.instructions.md`
4. **For specific features**: Check this index for relevant docs

---

## 📅 Latest Updates

- **May 17, 2026**: Added Historical Data Page (22-column analysis table)
  - Created `HISTORICAL_DATA_PAGE.md`
  - Created `HISTORICAL_DATA_CHANGES.md`
  - Updated `react-ui.instructions.md`
  - Updated `copilot-instructions.md`

---

## 🤝 Contributing to Documentation

When making code changes:
1. **Update relevant instruction file** in `.github/instructions/`
2. **Create feature doc** in `.github/docs/` for major features
3. **Update this index** with links to new docs
4. **Update copilot-instructions.md** if adding new pages or key files

All agents are configured to read these instruction files automatically when working in their respective domains.
