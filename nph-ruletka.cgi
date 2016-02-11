#!/usr/bin/env python3

import sys
import cgi
import os
import re
import json
import random
import pickle
import time

import cgitb
cgitb.enable()

from connect_db import db
import psycopg2

data = cgi.FieldStorage()

cgi.parse()
proto = os.environ['SERVER_PROTOCOL']
resource = re.sub('^.*/([^/]+)$', r'\1', os.environ['SCRIPT_NAME'])

class HttpException(Exception):
	def __init__(self, code, desc):
		self.text = "{} {}".format(code, desc)

def new_game():
	time.sleep(5)
	secure_random = random.SystemRandom()
	seed = secure_random.randint(0,2**20-1)
	score = 100
	rng = random.Random()
	rng.seed(seed)
	state = rng.getstate()
	success = False
	for i in range(0,16):
		session_id = secure_random.randint(1,2**31-1)
		try:
			with db.cursor() as cur:
				cur.execute("insert into sessions (id, seed, state, score) values(%s, %s, %s, %s)", (session_id, seed, pickle.dumps(state), score))
				db.commit()
			success = True
			break
		except Exception as e:
			db.rollback()
			print(e, file=sys.stderr)
			print(session_id, seed, score, file=sys.stderr)
	if not success:
		raise HttpException(500, 'Internal Server Error')
	return {'score': 100, 'token': session_id}

def bet():
	time.sleep(.5)
	if 'token' not in data:
		raise HttpException(400, 'Token is missing, call new_game first')
	session_id = int(data['token'].value)
	state = None
	score = None
	try:
		with db.cursor() as cur:
			cur.execute("select state, score from sessions where id=%s", (session_id,))
			state, score = cur.fetchone()
	except Exception as e:
		db.rollback()
		print(e, file=sys.stderr)
		raise HttpException(401, 'Invalid token')
	if score <= 0:
		raise HttpException(402, 'Listen, this event is pay to play, we all know this')
	if score >= 2e9:
		raise HttpException(418, "I'm a teapot")
	bet_type = None
	number = None
	bet = None
	if 'bet_type' in data:
		bet_type = data['bet_type'].value
	if 'number' in data:
		number = int(data['number'].value)
	if 'bet' in data:
		bet = int(data['bet'].value)
	if number is None or not 1 <= number <= 36:
		raise HttpException(400, 'Betting number must be in range 1..36')
	if bet is None or not 1 <= bet <= score:
		raise HttpException(400, 'Bet must be in range 1..score') 
	if not bet <= 10000:
		raise HttpException(400, 'Bet must be no greater than 10000') 
	rng = random.Random()
	rng.setstate(pickle.loads(state))
	winning = rng.randint(0, 36)
	state = rng.getstate()
	won = False
	score -= bet
	if winning == 0:
		pass
	elif bet_type == 'even_or_odd':
		won = (number%2 == winning%2)
		if won:
			score += 2*bet
	elif bet_type == 'single':
		won = (number == winning)
		if won:
			score += 36*bet
	else:
		raise HttpException(400, "Invalid bet type, valid types are `even_or_odd' and `single'")
	try:
		with db.cursor() as cur:
			cur.execute("insert into bets (session, type, number, winning, won, bet) values(%s, %s, %s, %s, %s, %s)", (session_id, bet_type, number, winning, won, bet))
			cur.execute("update sessions set state=%s,score=%s where id=%s", (pickle.dumps(state), score, session_id))
			db.commit()
	except Exception as e:
		db.rollback()
		print(e, file=sys.stderr)
		raise HttpException(500, 'Your game table was burnt by a dragon')
	return {'score': score, 'winning': winning, 'won': won}

try:
	result = None
	if resource == 'new_game':
		result = new_game()
	elif resource == 'bet':
		result = bet()
	if result is None:
		raise HttpException(404, 'Resource not found')
	print("{} 200 OK".format(proto))
	print("Content-Type: application/json")
	print()
	print(json.dumps(result))
except HttpException as e:
	print("{} {}".format(proto, e.text))
	print()
except BaseException as e:
	print("{} 500 {}".format(proto, e))
	print(e, file=sys.stderr)
	print()
