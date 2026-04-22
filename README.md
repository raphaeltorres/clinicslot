# Clinic Slot Installation

1. Extract the zip / clone repo
2. Go to project folder: 
```
cd clinicslot
```
4. Create env file: 
```
cp .env.example .env
```
6. Start everything: 
```
docker compose up --build
```
7. In another terminal, run migrations: 
```
docker compose exec web python manage.py migrate
```
9. Load fixtures / initial data:
```
    docker exec -it clinicslot_web python manage.py migrate
    docker exec -it clinicslot_web python manage.py loaddata initial_data
    docker exec -it clinicslot_web python manage.py generate_schedules --tenant=healthway.clinic --open=08:00 --close=12:00
```
7. Open in browser:
   http://localhost:8000
