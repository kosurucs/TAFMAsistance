import { useEffect, useState } from 'react';
import { useMarketStore } from '../../store';
import { fetchQuote } from '../../services/api';
import './MarketDepthTable.css';

export default function MarketDepthTable() {
  const { selectedSymbol, interval } = useMarketStore();
  const [depth, setDepth] = useState({ buy: [], sell: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    let intervalId;

    const loadDepth = async () => {
      if (!selectedSymbol) return;
      
      setLoading(true);
      setError(null);
      
      try {
        const { data, error: err } = await fetchQuote(selectedSymbol);
        if (err) {
          if (isMounted) {
            setError(err);
          }
          return;
        }
        if (isMounted && data && data.depth) {
          setDepth(data.depth);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Failed to load market depth');
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Load immediately
    loadDepth();

    // Refresh every 3 seconds (market depth is real-time)
    intervalId = setInterval(loadDepth, 3000);

    return () => {
      isMounted = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [selectedSymbol, interval]); // Reload when symbol or interval changes

  if (!selectedSymbol) {
    return (
      <div className="market-depth">
        <div className="market-depth__empty">
          Select a symbol to view market depth
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="market-depth">
        <div className="market-depth__error">
          {error}
        </div>
      </div>
    );
  }

  const buyOrders = depth.buy || [];
  const sellOrders = depth.sell || [];

  // Calculate total volumes
  const totalBuyQty = buyOrders.reduce((sum, o) => sum + (o.quantity || 0), 0);
  const totalSellQty = sellOrders.reduce((sum, o) => sum + (o.quantity || 0), 0);

  return (
    <div className="market-depth">
      <div className="market-depth__header">
        <h3>Market Depth — {selectedSymbol}</h3>
        <span className="market-depth__interval">Chart: {interval}</span>
      </div>

      {loading && <div className="market-depth__loading">Loading...</div>}

      <div className="market-depth__tables">
        {/* Buy Orders (Bids) */}
        <div className="market-depth__section market-depth__section--buy">
          <h4>Buy Orders (Bids)</h4>
          <table className="market-depth__table">
            <thead>
              <tr>
                <th>Orders</th>
                <th>Quantity</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              {buyOrders.length === 0 ? (
                <tr>
                  <td colSpan="3" className="market-depth__empty-cell">No data</td>
                </tr>
              ) : (
                buyOrders.map((order, idx) => (
                  <tr key={idx}>
                    <td>{order.orders || 0}</td>
                    <td>{(order.quantity || 0).toLocaleString()}</td>
                    <td className="market-depth__price market-depth__price--buy">
                      ₹{(order.price || 0).toFixed(2)}
                    </td>
                  </tr>
                ))
              )}
              {buyOrders.length > 0 && (
                <tr className="market-depth__total">
                  <td>Total</td>
                  <td><strong>{totalBuyQty.toLocaleString()}</strong></td>
                  <td></td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Sell Orders (Asks) */}
        <div className="market-depth__section market-depth__section--sell">
          <h4>Sell Orders (Asks)</h4>
          <table className="market-depth__table">
            <thead>
              <tr>
                <th>Price</th>
                <th>Quantity</th>
                <th>Orders</th>
              </tr>
            </thead>
            <tbody>
              {sellOrders.length === 0 ? (
                <tr>
                  <td colSpan="3" className="market-depth__empty-cell">No data</td>
                </tr>
              ) : (
                sellOrders.map((order, idx) => (
                  <tr key={idx}>
                    <td className="market-depth__price market-depth__price--sell">
                      ₹{(order.price || 0).toFixed(2)}
                    </td>
                    <td>{(order.quantity || 0).toLocaleString()}</td>
                    <td>{order.orders || 0}</td>
                  </tr>
                ))
              )}
              {sellOrders.length > 0 && (
                <tr className="market-depth__total">
                  <td></td>
                  <td><strong>{totalSellQty.toLocaleString()}</strong></td>
                  <td>Total</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
