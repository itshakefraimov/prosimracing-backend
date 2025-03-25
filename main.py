import os
import httpx
from dotenv import load_dotenv

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Field, SQLModel, create_engine, Session, select
from sqlalchemy import desc

load_dotenv() 

ACC_SERVER_URL = 'http://20.217.81.221:8080'

POSITION_POINTS = {
  1: 30,
  2: 26,
  3: 23,
  4: 20,
  5: 18,
  6: 16,
  7: 14,
  8: 12,
  9: 10,
  10: 8,
  11: 6,
  12: 5,
  13: 4,
  14: 3,
  15: 2
}

class LoadResultRequest(BaseModel):
  admin_password: str

class Standing(SQLModel, table=True):
  steam_id: str = Field(unique=True, primary_key=True)
  name: str
  short_name: str
  points: int = 0
  pole_positions: int = 0
  fastest_laps: int = 0

engine = create_engine(os.getenv('POSTGRESQL_URL'))
SQLModel.metadata.create_all(engine)

app = FastAPI()

origins = [
  '*',
]

app.add_middleware(
  CORSMiddleware,
  allow_origins=origins,
  allow_credentials=True,
  allow_methods=['POST', 'GET'],
  allow_headers=['*'],
)

@app.post('/load-result')
async def load_result(request: LoadResultRequest):
  admin_password = os.getenv('ADMIN_PASSWORD')

  if request.admin_password != admin_password:
    raise HTTPException(status_code=401, detail='Unauthorized')
  
  endpoint = f"{ACC_SERVER_URL}/api/results/list.json?q=R"

  async with httpx.AsyncClient() as client:
    response = await client.get(endpoint)
  
  if response.status_code != 200:
    raise HTTPException(status_code=response.status_code, detail='Failed to fetch list of results')
  
  result_json_url = response.json()['results'][0]['results_json_url']
  
  endpoint = f"{ACC_SERVER_URL}{result_json_url}"

  async with httpx.AsyncClient() as client:
    response = await client.get(endpoint)
      
  if response.status_code != 200:
    raise HTTPException(status_code=response.status_code, detail='Failed to fetch data')

  data = response.json()
  leaderboard_data = data['sessionResult']['leaderBoardLines']
  fastest_lap = data['sessionResult']['bestlap']
  db_standings = {}

  with Session(engine) as session:
    statement = select(Standing)
    result = session.exec(statement)

    for driver in result:
      db_standings[driver.steam_id] = driver

    for index, player in enumerate(leaderboard_data):
      steam_id = player['currentDriver']['playerId'][1:]

      if steam_id in db_standings:
        try:
          db_standings[steam_id].points += POSITION_POINTS[index + 1]
        except KeyError:
          pass
      else:
        name = (player['currentDriver']['firstName'] + ' ' + player['currentDriver']['lastName']).title()
        short_name = player['currentDriver']['shortName']
        try:
          points = POSITION_POINTS[index + 1]
        except KeyError:
          points = 0
        db_standings[steam_id] = Standing(steam_id=steam_id, name=name, short_name=short_name, points=points)

      player_fastest_lap = player['timing']['bestLap']

      if player_fastest_lap == fastest_lap:
        db_standings[steam_id].fastest_laps += 1
        db_standings[steam_id].points += 1

      session.add(db_standings[steam_id])
    
    session.commit()

  return 'OK'

@app.post('/load-result-qualifier')
async def load_result_qualifier(request: LoadResultRequest):
  admin_password = os.getenv('ADMIN_PASSWORD')

  if request.admin_password != admin_password:
    raise HTTPException(status_code=401, detail='Unauthorized')
  
  endpoint = f"{ACC_SERVER_URL}/api/results/list.json?q=Q"

  async with httpx.AsyncClient() as client:
    response = await client.get(endpoint)
  
  if response.status_code != 200:
    raise HTTPException(status_code=response.status_code, detail='Failed to fetch list of results')
  
  result_json_url = response.json()['results'][0]['results_json_url']
  
  endpoint = f"{ACC_SERVER_URL}{result_json_url}"

  async with httpx.AsyncClient() as client:
    response = await client.get(endpoint)
      
  if response.status_code != 200:
    raise HTTPException(status_code=response.status_code, detail='Failed to fetch data')

  data = response.json()
  leaderboard_data = data['sessionResult']['leaderBoardLines']
  fastest_lap = data['sessionResult']['bestlap']
  db_standings = {}

  with Session(engine) as session:
    statement = select(Standing)
    result = session.exec(statement)

    for driver in result:
      db_standings[driver.steam_id] = driver

    for index, player in enumerate(leaderboard_data):
      steam_id = player['currentDriver']['playerId'][1:]

      if not steam_id in db_standings:
        name = (player['currentDriver']['firstName'] + ' ' + player['currentDriver']['lastName']).title()
        short_name = player['currentDriver']['shortName']
        db_standings[steam_id] = Standing(steam_id=steam_id, name=name, short_name=short_name, points=0)

      player_fastest_lap = player['timing']['bestLap']

      if player_fastest_lap == fastest_lap:
        db_standings[steam_id].pole_positions += 1
        db_standings[steam_id].points += 1

      session.add(db_standings[steam_id])
    
    session.commit()

  return 'OK'

@app.get('/standings')
async def read_standings(limit: int = None):
  with Session(engine) as session:
    statement = select(Standing).order_by(desc(Standing.points)).limit(limit)
    result = session.exec(statement)
    return result.all()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app)
