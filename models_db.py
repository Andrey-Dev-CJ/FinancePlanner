from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import JSON

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(8), primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    consent_at = db.Column(db.DateTime)
    
    # Связь с конфигом
    config = db.relationship('UserConfig', back_populates='user', uselist=False, cascade='all, delete-orphan')

class UserConfig(db.Model):
    __tablename__ = 'user_configs'
    user_id = db.Column(db.String(8), db.ForeignKey('users.id'), primary_key=True)
    initial_balance = db.Column(db.Float, default=0.0)
    pay_days = db.Column(JSON, default=list)  # [5, 20]
    reserve_envelopes = db.Column(JSON, default=dict)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', back_populates='config')
    income_sources = db.relationship('IncomeSource', back_populates='config', cascade='all, delete-orphan')
    fixed_expenses = db.relationship('FixedExpense', back_populates='config', cascade='all, delete-orphan')
    variable_expenses = db.relationship('VariableExpense', back_populates='config', cascade='all, delete-orphan')
    events = db.relationship('Event', back_populates='config', cascade='all, delete-orphan')

class IncomeSource(db.Model):
    __tablename__ = 'income_sources'
    id = db.Column(db.String(8), primary_key=True)
    config_id = db.Column(db.String(8), db.ForeignKey('user_configs.user_id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    day_of_month = db.Column(db.Integer, nullable=False)
    active = db.Column(db.Boolean, default=True)
    
    config = db.relationship('UserConfig', back_populates='income_sources')

class FixedExpense(db.Model):
    __tablename__ = 'fixed_expenses'
    id = db.Column(db.String(8), primary_key=True)
    config_id = db.Column(db.String(8), db.ForeignKey('user_configs.user_id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    day_of_month = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(64), default='fixed')
    active = db.Column(db.Boolean, default=True)
    
    config = db.relationship('UserConfig', back_populates='fixed_expenses')

class VariableExpense(db.Model):
    __tablename__ = 'variable_expenses'
    id = db.Column(db.String(8), primary_key=True)
    config_id = db.Column(db.String(8), db.ForeignKey('user_configs.user_id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    amount_per_month = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(64), default='general')
    active = db.Column(db.Boolean, default=True)
    
    config = db.relationship('UserConfig', back_populates='variable_expenses')

class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.String(8), primary_key=True)
    config_id = db.Column(db.String(8), db.ForeignKey('user_configs.user_id'), nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(16), default='planned')
    category = db.Column(db.String(64), default='event')
    notes = db.Column(db.Text, default='')
    repeat = db.Column(db.String(16), default='')
    repeat_end = db.Column(db.Date, nullable=True)
    
    config = db.relationship('UserConfig', back_populates='events')