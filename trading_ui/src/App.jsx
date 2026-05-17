import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './design-system/theme.css';
import Dashboard from './pages/Dashboard';
import Portfolio from './pages/Portfolio';
import Backtest from './pages/Backtest';
import Simulate from './pages/Simulate';
import LLMStudio from './pages/LLMStudio';
import HistoricalData from './pages/HistoricalData';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/historical" element={<HistoricalData />} />
        <Route path="/backtest" element={<Backtest />} />
        <Route path="/simulate" element={<Simulate />} />
        <Route path="/llm-studio" element={<LLMStudio />} />
      </Routes>
    </BrowserRouter>
  );
}

