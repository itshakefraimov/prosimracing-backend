import os
import httpx

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from sqlmodel import Field, SQLModel, create_engine, Session, select

ACC_SERVER_URL = 'https://simsolutionil.emperorservers.com'

class LoadResultRequest(BaseModel):
  result: str
  admin_password: str

class Standing(SQLModel, table=True):
  steam_id: str = Field(unique=True, primary_key=True)
  name: str
  short_name: str
  points: int = 0

engine = create_engine(os.getenv('POSTGRESQL_URL'))
SQLModel.metadata.create_all(engine)

app = FastAPI()

@app.post('/load-result')
async def load_result(request: LoadResultRequest):
  admin_password = os.getenv('ADMIN_PASSWORD')

  if request.admin_password != admin_password:
    raise HTTPException(status_code=401, detail='Unauthorized')
  
  if not request.result or not request.result.endswith('.json'):
    raise HTTPException(status_code=400, detail='Result json is required')
  
  endpoint = f"{ACC_SERVER_URL}/results/download/{request.result}"

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
        db_standings[steam_id].points += index + 1
      else:
        name = (player['currentDriver']['firstName'] + ' ' + player['currentDriver']['lastName']).title()
        short_name = player['currentDriver']['shortName']
        points = len(leaderboard_data) - index
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