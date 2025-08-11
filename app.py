from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import os, random

# Optional yfinance
USE_YFINANCE = False
try:
    import yfinance as yf
    USE_YFINANCE = True
except Exception:
    USE_YFINANCE = False

from market_simulator import Market

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'teenvest-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///teenvest.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

market = Market(use_yfinance=False)

# ------------------------
# MODELS
# ------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    balance = db.Column(db.Float, default=100000.0)
    holdings = db.relationship('Holding', backref='owner', lazy=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), nullable=False)
    shares = db.Column(db.Float, nullable=False)
    avg_price = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class DailyRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    result_value = db.Column(db.Float, nullable=False)
    reward = db.Column(db.Float, default=0.0)

# ------------------------
# DB INIT + DEMO DATA
# ------------------------
with app.app_context():
    db.create_all()
    # Reset and add 100 demo players
    if User.query.count() == 0:
        for i in range(1, 101):
            u = User(
                name=f"Demo{i:03d}",
                email=f"demo{i:03d}@example.com"
            )
            u.set_password("demo")
            u.balance = round(50000 + random.random() * 200000, 2)
            db.session.add(u)
        db.session.commit()

# ------------------------
# STATIC ROUTES
# ------------------------
@app.route('/assets/<path:filename>')
def assets(filename):
    return send_from_directory('static/assets', filename)

# ------------------------
# BASIC ROUTES
# ------------------------
@app.route('/')
def index():
    snapshot = market.get_snapshot(['INFY', 'TCS', 'RELI', 'AAPL', 'TSLA', 'BTC', 'ETH', 'DOGE'])
    return render_template('index.html', snapshot=snapshot, live=session.get('live', False), use_yfinance=USE_YFINANCE)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/tutorials')
def tutorials():
    return render_template('tutorials.html')

@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    questions = [
        {
            "question": "What does IPO stand for?",
            "options": ["Initial Public Offering", "International Price Order", "Investment Portfolio Option"],
            "answer": "Initial Public Offering"
        },
        {
            "question": "Which is a cryptocurrency?",
            "options": ["AAPL", "BTC", "TSLA"],
            "answer": "BTC"
        },
        {
            "question": "What is a stock symbol?",
            "options": ["A unique code for a company", "A type of bond", "A trading strategy"],
            "answer": "A unique code for a company"
        },
        {
            "question": "Which market is known for technology stocks?",
            "options": ["NASDAQ", "NYSE", "BSE"],
            "answer": "NASDAQ"
        },
        {
            "question": "What does 'bull market' mean?",
            "options": ["Rising prices", "Falling prices", "Stable prices"],
            "answer": "Rising prices"
        },
        {
            "question": "Which company is NOT a tech company?",
            "options": ["Apple", "Tesla", "Coca-Cola"],
            "answer": "Coca-Cola"
        },
        {
            "question": "What is diversification?",
            "options": ["Investing in one stock", "Spreading investments", "Selling all assets"],
            "answer": "Spreading investments"
        },
        {
            "question": "Which is a type of order in trading?",
            "options": ["Limit order", "Stop order", "Both of the above"],
            "answer": "Both of the above"
        }
    ]
    score = None
    if request.method == 'POST':
        user_answers = [request.form.get(f'q{i}') for i in range(len(questions))]
        score = sum([user_answers[i] == questions[i]['answer'] for i in range(len(questions))])
    return render_template('quiz.html', questions=questions, score=score)

# ------------------------
# AUTH ROUTES
# ------------------------
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '').lower()
        pw = request.form.get('password', '')

        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'warning')
            return redirect(url_for('register'))

        u = User(name=name, email=email)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()

        session['user_id'] = u.id
        flash('Account created — ₹100,000 credited', 'success')
        return redirect(url_for('portfolio'))

    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').lower()
        pw = request.form.get('password', '')
        u = User.query.filter_by(email=email).first()
        if not u or not u.check_password(pw):
            flash('Invalid credentials', 'danger')
            return redirect(url_for('login'))
        session['user_id'] = u.id
        flash(f'Welcome back, {u.name}', 'success')
        return redirect(url_for('portfolio'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('index'))

# ------------------------
# PORTFOLIO & TRADING
# ------------------------
@app.route('/portfolio')
def portfolio():
    if 'user_id' not in session:
        flash('Login to view portfolio', 'info')
        return redirect(url_for('login'))
    u = User.query.get(session['user_id'])
    holdings = []
    total_hold = 0
    for h in u.holdings:
        price = market.get_price(h.symbol)
        val = price * h.shares
        total_hold += val
        holdings.append({
            'symbol': h.symbol,
            'shares': h.shares,
            'avg': h.avg_price,
            'price': round(price, 6 if h.symbol in ['DOGE'] else 2),
            'value': round(val, 2)
        })
    net = round(u.balance + total_hold, 2)
    return render_template('portfolio.html', user=u, holdings=holdings, net=net, live=session.get('live', False))

@app.route('/trade', methods=['GET', 'POST'])
def trade_page():
    if 'user_id' not in session:
        flash('Login to trade', 'info')
        return redirect(url_for('login'))
    snapshot = market.get_snapshot(['INFY', 'TCS', 'RELI', 'AAPL', 'TSLA', 'BTC', 'ETH', 'DOGE'])
    u = User.query.get(session['user_id'])

    if request.method == 'POST':
        symbol = request.form.get('asset')  # matches form field
        action = request.form.get('action')
        try:
            amount = float(request.form.get('quantity', 0))
        except ValueError:
            amount = 0
        price = market.get_price(symbol)

        if action == 'buy' and amount > 0:
            cost = price * amount
            if u.balance >= cost:
                u.balance -= cost
                holding = Holding.query.filter_by(user_id=u.id, symbol=symbol).first()
                if holding:
                    total_shares = holding.shares + amount
                    holding.avg_price = (holding.avg_price * holding.shares + price * amount) / total_shares
                    holding.shares = total_shares
                else:
                    holding = Holding(symbol=symbol, shares=amount, avg_price=price, owner=u)
                    db.session.add(holding)
                db.session.commit()
                flash(f'Bought {amount} shares of {symbol} at ₹{price:.2f}', 'success')
            else:
                flash('Insufficient balance', 'danger')

        elif action == 'sell' and amount > 0:
            holding = Holding.query.filter_by(user_id=u.id, symbol=symbol).first()
            if holding and holding.shares >= amount:
                proceeds = price * amount
                u.balance += proceeds
                holding.shares -= amount
                if holding.shares == 0:
                    db.session.delete(holding)
                db.session.commit()
                flash(f'Sold {amount} shares of {symbol} at ₹{price:.2f}', 'success')
            else:
                flash('Not enough shares to sell', 'danger')

        else:
            flash('Invalid trade', 'danger')

        market.simulate_movement(symbol)
        return redirect(url_for('portfolio'))

    return render_template('trade.html', snapshot=snapshot, live=session.get('live', False))

@app.route('/trade-game', methods=['GET', 'POST'])
def trade_game():
    # Simple session-based fake money and holdings
    if 'fake_balance' not in session:
        session['fake_balance'] = 100000
        session['fake_holdings'] = {}
    message = None
    stocks = ['AAPL', 'TSLA', 'INFY', 'TCS', 'BTC', 'ETH', 'DOGE']
    prices = market.get_snapshot(stocks)
    if request.method == 'POST':
        symbol = request.form.get('symbol')
        action = request.form.get('action')
        amount = int(request.form.get('amount', 0))
        price = prices[symbol]['price']
        holdings = session['fake_holdings']
        balance = session['fake_balance']
        if action == 'buy' and amount > 0 and balance >= price * amount:
            holdings[symbol] = holdings.get(symbol, 0) + amount
            session['fake_balance'] = balance - price * amount
            message = f"Bought {amount} shares of {symbol}!"
        elif action == 'sell' and amount > 0 and holdings.get(symbol, 0) >= amount:
            holdings[symbol] -= amount
            session['fake_balance'] = balance + price * amount
            message = f"Sold {amount} shares of {symbol}!"
        else:
            message = "Invalid transaction."
        session['fake_holdings'] = holdings
    holdings = session.get('fake_holdings', {})
    balance = session.get('fake_balance', 100000)
    return render_template('trade_game.html', stocks=stocks, prices=prices, holdings=holdings, balance=balance, message=message)

# ------------------------
# LEADERBOARD
# ------------------------
@app.route('/leaderboard')
def leaderboard():
    names = [
        "Aryan", "Diya", "Kabir", "Maya", "Rohan", "Aanya", "Vivaan", "Sara",
        "Aditya", "Isha", "Krish", "Meera", "Yash", "Tara", "Arjun", "Riya"
    ]
    leaderboard = []
    for i in range(10):
        leaderboard.append({
            "name": random.choice(names),
            "net_worth": round(random.uniform(90000, 200000), 2)
        })
    # Sort by net worth descending
    leaderboard = sorted(leaderboard, key=lambda x: x['net_worth'], reverse=True)
    return render_template('leaderboard.html', leaderboard=leaderboard)

# ------------------------
# CRYPTO
# ------------------------
@app.route('/crypto')
def crypto():
    return render_template('crypto.html')

@app.route('/crypto-game', methods=['GET', 'POST'])
def crypto_game():
    cryptos = ['BTC', 'ETH', 'DOGE']
    result = None
    symbol = 'BTC'
    guess = None
    if request.method == 'POST':
        symbol = request.form.get('symbol', 'BTC')
        guess = request.form.get('guess', 'up')
        snapshot = market.get_snapshot([symbol])
        price = snapshot[symbol]['price']
        new_price, movement = market.simulate_movement(symbol)
        if (movement > 0 and guess == 'up') or (movement < 0 and guess == 'down'):
            result = f'Correct! {symbol} moved to ₹{new_price:.2f}.'
        else:
            result = f'Incorrect! {symbol} moved to ₹{new_price:.2f}.'
    return render_template('crypto_game.html', result=result, symbol=symbol, guess=guess, cryptos=cryptos)

# ------------------------
# DAILY CHALLENGE
# ------------------------
@app.route('/daily')
def daily():
    today = date.today()
    seed = today.toordinal() % 10 + 5
    start = 5000
    target = round(start * (1 + seed / 100.0), 2)
    done = False
    record = None
    if 'user_id' in session:
        record = DailyRecord.query.filter_by(user_id=session['user_id'], date=today).first()
        if record:
            done = True
    return render_template('daily.html', start=start, target=target, duration=120, done=done, record=record)

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/assets', 'favicon.ico')

@app.route('/game', methods=['GET', 'POST'])
def game():
    result = None
    symbol = 'AAPL'
    guess = None
    if request.method == 'POST':
        symbol = request.form.get('symbol', 'AAPL')
        guess = request.form.get('guess', 'up')
        snapshot = market.get_snapshot([symbol])
        price = snapshot[symbol]['price']
        new_price, movement = market.simulate_movement(symbol)
        if (movement > 0 and guess == 'up') or (movement < 0 and guess == 'down'):
            result = f'Correct! {symbol} moved to ₹{new_price:.2f}.'
        else:
            result = f'Incorrect! {symbol} moved to ₹{new_price:.2f}.'
    return render_template('game.html', result=result, symbol=symbol, guess=guess)

@app.route('/games')
def games():
    return render_template('games.html')

if __name__ == '__main__':
    app.run(debug=True)

