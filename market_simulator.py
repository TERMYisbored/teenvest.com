import random

class Market:
    def __init__(self, use_yfinance=False):
        self.use_yfinance = use_yfinance
        # Demo prices for stocks/crypto
        self.prices = {
            'AAPL': 180.0,
            'TSLA': 250.0,
            'INFY': 1600.0,
            'TCS': 3700.0,
            'RELI': 2900.0,
            'BTC': 65000.0,
            'ETH': 3500.0,
            'DOGE': 0.15
        }

    def get_snapshot(self, symbols):
        # Returns current prices for requested symbols
        snapshot = {}
        for symbol in symbols:
            price = self.prices.get(symbol, 100.0)
            snapshot[symbol] = {'price': round(price, 2)}
        return snapshot

    def simulate_movement(self, symbol):
        # Simulate price movement for the game
        price = self.prices.get(symbol, 100.0)
        movement = random.choice([-0.01, 0.01])  # -1% or +1%
        new_price = price * (1 + movement)
        self.prices[symbol] = new_price
        return round(new_price, 2), movement

    def update_prices(self):
        # Randomly update all prices (for demo)
        for symbol in self.prices:
            movement = random.uniform(-0.02, 0.02)  # -2% to +2%
            self.prices[symbol] *= (1 + movement)
            self.prices[symbol] = round(self.prices[symbol], 2)

    def get_price(self, symbol):
        """Return the current price for a given symbol."""
        return self.prices.get(symbol, 100.0)
