import os
import httpx
from dotenv import load_dotenv

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Field, SQLModel, create_engine, Session, select

load_dotenv() 

ACC_SERVER_URL = 'https://simsolutionil.emperorservers.com'

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

engine = create_engine(os.getenv('POSTGRESQL_URL'))
SQLModel.metadata.create_all(engine)

app = FastAPI()

origins = [
  'https://prosimracing-frontend.vercel.app/',
  'http://localhost:3000',
  'http://localhost:8000'
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

      session.add(db_standings[steam_id])
    
    session.commit()

  return 'OK'

@app.get('/standings')
async def read_standings():
  with Session(engine) as session:
    statement = select(Standing)
    result = session.exec(statement)
    return sorted(result, key=lambda x: x.points, reverse=True)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app)