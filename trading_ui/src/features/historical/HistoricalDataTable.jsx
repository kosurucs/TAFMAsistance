import { useEffect, useState } from 'react';
import { fetchMarketData } from '../../services/api';
import { Spinner } from '../../design-system';
import './HistoricalDataTable.css';

export function HistoricalDataTable({ symbol, interval, limit, tradeType }) {
  const [candles, setCandles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      if (!symbol) return;

      setLoading(true);
      setError(null);

      try {
        const { data, error: err } = await fetchMarketData(symbol, interval, limit);
        
        if (err) {
          if (isMounted) {
            setError(err);
          }
          return;
        }

        if (isMounted && data && data.candles) {
          setCandles(data.candles);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to load historical data');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    loadData();

    return () => {
      isMounted = false;
    };
  }, [symbol, interval, limit]);

  // Helper function - define before calculations
  const getCandleType = (candle) => {
    return candle.close >= candle.open ? 'bullish' : 'bearish';
  };

  // Format timestamp to IST datetime string
  const formatTimestamp = (timestamp) => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  // Format number to 2 decimal places with commas
  const formatNumber = (num) => {
    return num.toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  // Format volume with commas
  const formatVolume = (vol) => {
    return vol.toLocaleString('en-IN');
  };

  // Calculate volume building metrics
  const calculateVolumeBuilding = (candles) => {
    const results = [];
    let cumulativeBullishVol = 0;
    let cumulativeBearishVol = 0;
    let dayStartIndex = 0;

    // Group by day for intraday intervals
    const isIntraday = ['minute', '5minute', '15minute', '30minute', '60minute'].includes(interval);

    candles.forEach((candle, index) => {
      const candleType = candle.close >= candle.open ? 'bullish' : 'bearish';
      const date = new Date(candle.time * 1000);
      const hour = date.getHours();
      const minute = date.getMinutes();

      // Check if this is start of new day (9:15 AM IST or first candle of day)
      if (isIntraday && index > 0) {
        const prevDate = new Date(candles[index - 1].time * 1000);
        if (date.getDate() !== prevDate.getDate() || (hour === 9 && minute === 15)) {
          // Reset cumulative volumes for new day
          cumulativeBullishVol = 0;
          cumulativeBearishVol = 0;
          dayStartIndex = index;
        }
      }

      // Add to cumulative volume based on candle type
      if (candleType === 'bullish') {
        cumulativeBullishVol += candle.volume;
      } else {
        cumulativeBearishVol += candle.volume;
      }

      // Determine volume building direction
      const netVolume = cumulativeBullishVol - cumulativeBearishVol;
      const volumeDirection = netVolume > 0 ? 'Bullish' : netVolume < 0 ? 'Bearish' : 'Neutral';
      
      // Check for trend change from previous candle
      let trendChange = '';
      if (index > dayStartIndex) {
        const prevResult = results[index - 1];
        if (prevResult && prevResult.volumeDirection !== volumeDirection) {
          trendChange = `${prevResult.volumeDirection} → ${volumeDirection}`;
        }
      }

      results.push({
        cumulativeBullishVol,
        cumulativeBearishVol,
        netVolume,
        volumeDirection,
        trendChange,
        totalDayVolume: cumulativeBullishVol + cumulativeBearishVol,
      });
    });

    return results;
  };

  const volumeMetrics = candles.length > 0 ? calculateVolumeBuilding(candles) : [];

  // Calculate technical indicators and trading strategies
  const calculateTechnicalIndicators = (candles) => {
    const results = [];
    
    candles.forEach((candle, index) => {
      const indicators = {};
      
      // Basic candle metrics
      const candleBody = Math.abs(candle.close - candle.open);
      const candleRange = candle.high - candle.low;
      const upperWick = candle.high - Math.max(candle.open, candle.close);
      const lowerWick = Math.min(candle.open, candle.close) - candle.low;
      
      indicators.bodyPercent = candleRange > 0 ? (candleBody / candleRange * 100) : 0;
      indicators.upperWickPercent = candleRange > 0 ? (upperWick / candleRange * 100) : 0;
      indicators.lowerWickPercent = candleRange > 0 ? (lowerWick / candleRange * 100) : 0;
      indicators.rangePercent = candle.open > 0 ? (candleRange / candle.open * 100) : 0;
      
      // RSI Calculation (14 period)
      if (index >= 14) {
        let gains = 0, losses = 0;
        for (let i = index - 13; i <= index; i++) {
          const change = candles[i].close - candles[i].open;
          if (change > 0) gains += change;
          else losses += Math.abs(change);
        }
        const avgGain = gains / 14;
        const avgLoss = losses / 14;
        indicators.rsi = avgLoss === 0 ? 100 : 100 - (100 / (1 + (avgGain / avgLoss)));
      } else {
        indicators.rsi = null;
      }
      
      // Moving Averages
      if (index >= 19) {
        // SMA 20
        let sum = 0;
        for (let i = index - 19; i <= index; i++) {
          sum += candles[i].close;
        }
        indicators.sma20 = sum / 20;
        indicators.distanceFromSMA20 = ((candle.close - indicators.sma20) / indicators.sma20 * 100);
      } else {
        indicators.sma20 = null;
        indicators.distanceFromSMA20 = null;
      }
      
      if (index >= 9) {
        // SMA 10 (fast MA)
        let sum = 0;
        for (let i = index - 9; i <= index; i++) {
          sum += candles[i].close;
        }
        indicators.sma10 = sum / 10;
      } else {
        indicators.sma10 = null;
      }
      
      // Volume analysis
      if (index >= 19) {
        let volSum = 0;
        for (let i = index - 19; i <= index; i++) {
          volSum += candles[i].volume;
        }
        const avgVolume = volSum / 20;
        indicators.volumeRatio = avgVolume > 0 ? (candle.volume / avgVolume) : 1;
      } else {
        indicators.volumeRatio = null;
      }
      
      // Trend direction (based on MAs)
      if (indicators.sma10 && indicators.sma20) {
        if (indicators.sma10 > indicators.sma20 && candle.close > indicators.sma20) {
          indicators.trend = 'Strong Uptrend';
        } else if (indicators.sma10 > indicators.sma20) {
          indicators.trend = 'Uptrend';
        } else if (indicators.sma10 < indicators.sma20 && candle.close < indicators.sma20) {
          indicators.trend = 'Strong Downtrend';
        } else if (indicators.sma10 < indicators.sma20) {
          indicators.trend = 'Downtrend';
        } else {
          indicators.trend = 'Sideways';
        }
      } else {
        indicators.trend = 'N/A';
      }
      
      // Candle pattern recognition
      indicators.pattern = 'Normal';
      
      // Doji (small body, long wicks)
      if (indicators.bodyPercent < 5) {
        indicators.pattern = 'Doji';
      }
      // Hammer (small body at top, long lower wick)
      else if (indicators.bodyPercent < 30 && indicators.lowerWickPercent > 60) {
        indicators.pattern = 'Hammer';
      }
      // Shooting Star (small body at bottom, long upper wick)
      else if (indicators.bodyPercent < 30 && indicators.upperWickPercent > 60) {
        indicators.pattern = 'Shooting Star';
      }
      // Strong Candle (large body, small wicks)
      else if (indicators.bodyPercent > 70) {
        indicators.pattern = getCandleType(candle) === 'bullish' ? 'Strong Bull' : 'Strong Bear';
      }
      
      // Engulfing pattern (needs previous candle)
      if (index > 0) {
        const prevCandle = candles[index - 1];
        const prevType = getCandleType(prevCandle);
        const currType = getCandleType(candle);
        
        if (currType === 'bullish' && prevType === 'bearish' &&
            candle.close > prevCandle.open && candle.open < prevCandle.close) {
          indicators.pattern = 'Bullish Engulfing';
        } else if (currType === 'bearish' && prevType === 'bullish' &&
                   candle.close < prevCandle.open && candle.open > prevCandle.close) {
          indicators.pattern = 'Bearish Engulfing';
        }
      }
      
      // Trading Signal
      indicators.signal = 'HOLD';
      let signalStrength = 0;
      
      // RSI signals
      if (indicators.rsi) {
        if (indicators.rsi < 30) {
          signalStrength += 2; // Oversold
        } else if (indicators.rsi > 70) {
          signalStrength -= 2; // Overbought
        }
      }
      
      // Trend signals
      if (indicators.trend === 'Strong Uptrend') signalStrength += 2;
      else if (indicators.trend === 'Uptrend') signalStrength += 1;
      else if (indicators.trend === 'Strong Downtrend') signalStrength -= 2;
      else if (indicators.trend === 'Downtrend') signalStrength -= 1;
      
      // Volume confirmation
      if (indicators.volumeRatio && indicators.volumeRatio > 1.5) {
        const candleType = getCandleType(candle);
        if (candleType === 'bullish') signalStrength += 1;
        else signalStrength -= 1;
      }
      
      // Pattern signals
      if (indicators.pattern === 'Bullish Engulfing' || indicators.pattern === 'Hammer') {
        signalStrength += 2;
      } else if (indicators.pattern === 'Bearish Engulfing' || indicators.pattern === 'Shooting Star') {
        signalStrength -= 2;
      }
      
      // Final signal determination
      if (signalStrength >= 3) {
        indicators.signal = 'STRONG BUY';
      } else if (signalStrength >= 1) {
        indicators.signal = 'BUY';
      } else if (signalStrength <= -3) {
        indicators.signal = 'STRONG SELL';
      } else if (signalStrength <= -1) {
        indicators.signal = 'SELL';
      }
      
      indicators.signalStrength = signalStrength;
      
      results.push(indicators);
    });
    
    return results;
  };
  
  const technicalIndicators = candles.length > 0 ? calculateTechnicalIndicators(candles) : [];

  if (!symbol) {
    return (
      <div className="historical-table__empty">
        Select a symbol to view historical data
      </div>
    );
  }

  if (loading) {
    return (
      <div className="historical-table__loading">
        <Spinner />
        <span>Loading historical data...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="historical-table__error">
        {error}
      </div>
    );
  }

  if (!candles || candles.length === 0) {
    return (
      <div className="historical-table__empty">
        No historical data available for {symbol}
      </div>
    );
  }

  return (
    <div className="historical-table">
      <div className="historical-table__info">
        Showing {candles.length} candles for <strong>{symbol}</strong> ({interval}) - Trade Type: <strong>{tradeType}</strong>
      </div>
      
      <table className="historical-table__table">
        <thead>
          <tr>
            <th className="historical-table__th">#</th>
            <th className="historical-table__th historical-table__th--timestamp">Timestamp (IST)</th>
            <th className="historical-table__th historical-table__th--price">Open</th>
            <th className="historical-table__th historical-table__th--price">High</th>
            <th className="historical-table__th historical-table__th--price">Low</th>
            <th className="historical-table__th historical-table__th--price">Close</th>
            <th className="historical-table__th historical-table__th--volume">Volume</th>
            <th className="historical-table__th">Type</th>
            <th className="historical-table__th historical-table__th--price">Change %</th>
            
            {/* Volume Analysis */}
            <th className="historical-table__th historical-table__th--volume">Vol Ratio</th>
            <th className="historical-table__th historical-table__th--volume">Bull Vol</th>
            <th className="historical-table__th historical-table__th--volume">Bear Vol</th>
            <th className="historical-table__th">Vol Build</th>
            
            {/* Technical Indicators */}
            <th className="historical-table__th">RSI(14)</th>
            <th className="historical-table__th historical-table__th--price">SMA(20)</th>
            <th className="historical-table__th">% from SMA</th>
            <th className="historical-table__th">Trend</th>
            
            {/* Candle Analysis */}
            <th className="historical-table__th">Body %</th>
            <th className="historical-table__th">Range %</th>
            <th className="historical-table__th">Pattern</th>
            
            {/* Trading Signal */}
            <th className="historical-table__th">Signal</th>
            <th className="historical-table__th">Strength</th>
          </tr>
        </thead>
        <tbody>
          {candles.map((candle, index) => {
            const candleType = getCandleType(candle);
            const change = candle.close - candle.open;
            const changePercent = ((change / candle.open) * 100);
            const volMetric = volumeMetrics[index] || {};
            const indicators = technicalIndicators[index] || {};

            return (
              <tr 
                key={candle.time} 
                className={`historical-table__row historical-table__row--${candleType}`}
              >
                <td className="historical-table__td historical-table__td--index">
                  {candles.length - index}
                </td>
                <td className="historical-table__td historical-table__td--timestamp">
                  {formatTimestamp(candle.time)}
                </td>
                <td className="historical-table__td historical-table__td--price">
                  ₹{formatNumber(candle.open)}
                </td>
                <td className="historical-table__td historical-table__td--price historical-table__td--high">
                  ₹{formatNumber(candle.high)}
                </td>
                <td className="historical-table__td historical-table__td--price historical-table__td--low">
                  ₹{formatNumber(candle.low)}
                </td>
                <td className="historical-table__td historical-table__td--price">
                  ₹{formatNumber(candle.close)}
                </td>
                <td className="historical-table__td historical-table__td--volume">
                  {formatVolume(candle.volume)}
                </td>
                <td className={`historical-table__td historical-table__td--type historical-table__td--${candleType}`}>
                  {candleType === 'bullish' ? '🟢 Bull' : '🔴 Bear'}
                </td>
                <td className={`historical-table__td historical-table__td--change historical-table__td--${change >= 0 ? 'positive' : 'negative'}`}>
                  <span className="historical-table__change-percent">
                    {change >= 0 ? '+' : ''}{changePercent.toFixed(2)}%
                  </span>
                </td>
                
                {/* Volume Analysis */}
                <td className="historical-table__td historical-table__td--volume">
                  {indicators.volumeRatio ? (
                    <span className={indicators.volumeRatio > 1.5 ? 'volume-spike' : ''}>
                      {indicators.volumeRatio.toFixed(2)}x
                    </span>
                  ) : 'N/A'}
                </td>
                <td className="historical-table__td historical-table__td--volume historical-table__td--bullish">
                  {formatVolume(volMetric.cumulativeBullishVol || 0)}
                </td>
                <td className="historical-table__td historical-table__td--volume historical-table__td--bearish">
                  {formatVolume(volMetric.cumulativeBearishVol || 0)}
                </td>
                <td className={`historical-table__td historical-table__td--vol-direction historical-table__td--${(volMetric.volumeDirection || '').toLowerCase()}`}>
                  <div className="vol-direction-badge">
                    {volMetric.volumeDirection === 'Bullish' && '📈 '}
                    {volMetric.volumeDirection === 'Bearish' && '📉 '}
                    {volMetric.volumeDirection || 'N/A'}
                  </div>
                  <div className="vol-direction-net">
                    Net: {volMetric.netVolume ? formatVolume(Math.abs(volMetric.netVolume)) : '0'}
                  </div>
                </td>
                
                {/* Technical Indicators */}
                <td className={`historical-table__td historical-table__td--rsi ${
                  indicators.rsi 
                    ? indicators.rsi < 30 ? 'oversold' 
                    : indicators.rsi > 70 ? 'overbought' 
                    : '' 
                    : ''
                }`}>
                  {indicators.rsi ? indicators.rsi.toFixed(1) : 'N/A'}
                </td>
                <td className="historical-table__td historical-table__td--price">
                  {indicators.sma20 ? `₹${formatNumber(indicators.sma20)}` : 'N/A'}
                </td>
                <td className={`historical-table__td ${
                  indicators.distanceFromSMA20 
                    ? indicators.distanceFromSMA20 > 0 ? 'historical-table__td--positive' : 'historical-table__td--negative'
                    : ''
                }`}>
                  {indicators.distanceFromSMA20 
                    ? `${indicators.distanceFromSMA20 > 0 ? '+' : ''}${indicators.distanceFromSMA20.toFixed(2)}%`
                    : 'N/A'}
                </td>
                <td className={`historical-table__td historical-table__td--trend historical-table__td--${
                  indicators.trend.includes('Up') ? 'uptrend' 
                  : indicators.trend.includes('Down') ? 'downtrend' 
                  : 'sideways'
                }`}>
                  {indicators.trend.includes('Strong Up') && '🚀 '}
                  {indicators.trend.includes('Strong Down') && '💥 '}
                  {indicators.trend === 'Uptrend' && '📈 '}
                  {indicators.trend === 'Downtrend' && '📉 '}
                  {indicators.trend}
                </td>
                
                {/* Candle Analysis */}
                <td className="historical-table__td">
                  {indicators.bodyPercent ? `${indicators.bodyPercent.toFixed(1)}%` : 'N/A'}
                </td>
                <td className="historical-table__td">
                  {indicators.rangePercent ? `${indicators.rangePercent.toFixed(2)}%` : 'N/A'}
                </td>
                <td className={`historical-table__td historical-table__td--pattern ${
                  indicators.pattern.includes('Engulfing') || indicators.pattern.includes('Hammer') || indicators.pattern.includes('Shooting')
                    ? 'pattern-significant'
                    : ''
                }`}>
                  {indicators.pattern === 'Bullish Engulfing' && '🟢🟢 '}
                  {indicators.pattern === 'Bearish Engulfing' && '🔴🔴 '}
                  {indicators.pattern === 'Hammer' && '🔨 '}
                  {indicators.pattern === 'Shooting Star' && '⭐ '}
                  {indicators.pattern === 'Doji' && '➕ '}
                  {indicators.pattern}
                </td>
                
                {/* Trading Signal */}
                <td className={`historical-table__td historical-table__td--signal ${
                  indicators.signal.includes('BUY') ? 'signal-buy'
                  : indicators.signal.includes('SELL') ? 'signal-sell'
                  : 'signal-hold'
                }`}>
                  <div className="signal-badge">
                    {indicators.signal === 'STRONG BUY' && '🟢🟢 '}
                    {indicators.signal === 'BUY' && '🟢 '}
                    {indicators.signal === 'STRONG SELL' && '🔴🔴 '}
                    {indicators.signal === 'SELL' && '🔴 '}
                    {indicators.signal === 'HOLD' && '⚪ '}
                    {indicators.signal}
                  </div>
                </td>
                <td className={`historical-table__td historical-table__td--strength ${
                  indicators.signalStrength > 0 ? 'strength-positive'
                  : indicators.signalStrength < 0 ? 'strength-negative'
                  : 'strength-neutral'
                }`}>
                  {indicators.signalStrength > 0 ? '+' : ''}{indicators.signalStrength}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
