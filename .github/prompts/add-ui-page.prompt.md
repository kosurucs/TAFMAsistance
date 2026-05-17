---
description: "Scaffold a new page in the React trading UI with all required layers: page component, feature folder, navigation entry, API service functions, and zustand store slice."
---

Create a new UI page named `${input:pageName}` in the trading UI.

## Steps

### 1. Create the Page Component

Create `trading_ui/src/pages/${input:pageName}.jsx`:
- Import layout from `layouts/AppLayout`
- Import feature components from `features/${input:pageName|lower}/`
- Use CSS vars from `theme.css` — no hardcoded values
- Wrap in `<ErrorBoundary>`

### 2. Create the Feature Folder

Create `trading_ui/src/features/${input:pageName|lower}/`:
- `index.js` — barrel export of all feature components
- `${input:pageName}Page.jsx` — main feature component
- Additional sub-components as needed

### 3. Add to Navigation

Open `trading_ui/src/layouts/Header.jsx`:
- Add a new nav tab: `{ label: '${input:pageName}', path: '/${input:pageName|lower}' }`
- Follow the existing active-state styling pattern using CSS vars

### 4. Add Route

Open `trading_ui/src/App.jsx` (or the router file):
- Import the new page component
- Add a `<Route path="/${input:pageName|lower}" element={<${input:pageName} />} />` entry

### 5. Add API Service Functions

Open `trading_ui/src/services/api.js`:
- Add any new API functions needed by this page
- Pattern: `export async function fetch${input:pageName}Data(params) { ... return { data, error }; }`
- All functions must return `{ data, error }` — never throw

### 6. Add Zustand Store Slice

Create `trading_ui/src/store/${input:pageName|lower}Store.js`:
```javascript
import { create } from 'zustand'

export const use${input:pageName}Store = create((set) => ({
  data: null,
  loading: false,
  error: null,
  setData: (data) => set({ data }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}))
```

### 7. Add Custom Hook

Create `trading_ui/src/hooks/use${input:pageName}.js`:
- Wraps the API call + store update
- Handles loading, error, and success states
- Example: `export function use${input:pageName}() { const { setData, setLoading, setError } = use${input:pageName}Store(); ... }`

### 8. Sync Docs

After completing, run the `doc-sync` agent to update `react-ui.instructions.md` with the new page in the Five Pages table.

## Validation

- `cd trading_ui && npm run dev` — page loads without console errors
- Page appears in the navigation with correct active state highlighting
- All CSS values use CSS vars (search for `#` or hardcoded `px` values in the new files)
