"""Creates fake API responses in the real formats, so the pipeline can be tested offline."""
import json, random, os
random.seed(1)
D = os.path.join(os.path.dirname(__file__), "fixtures")
kinds = [({"amenity":"restaurant","cuisine":"japanese;sushi"},"Sushi"),({"amenity":"cafe","dog":"yes","outdoor_seating":"yes"},"Kopi"),
         ({"amenity":"bar","opening_hours":"24/7"},"Bar"),({"shop":"mall","wheelchair":"yes"},"Mall"),({"tourism":"museum"},"Museum"),
         ({"leisure":"park","dog":"leashed"},"Park"),({"natural":"beach"},"Beach"),({"amenity":"food_court"},"Food Court"),
         ({"amenity":"restaurant","diet:vegetarian":"only","cuisine":"indian"},"Veg"),({"amenity":"bank"},"Bank")]
els = []
for i in range(400):
    tags, nm = kinds[i % len(kinds)]
    lat, lng = 1.28 + random.random()*0.14, 103.70 + random.random()*0.25
    t = dict(tags, name=f"{nm} {i}")
    if i % 3 == 0: els.append({"type":"way","id":i,"center":{"lat":lat,"lon":lng},"tags":t})
    else: els.append({"type":"node","id":i,"lat":lat,"lon":lng,"tags":t})
# a real-looking duplicate of a manual listing, to test merging
els.append({"type":"node","id":9001,"lat":1.28525,"lon":103.83255,"tags":{"amenity":"food_court","name":"Tiong Bahru Market"}})
els.append({"type":"node","id":9002,"lat":1.29152,"lon":103.83948,"tags":{"amenity":"cafe","name":"Common Man Coffee Roasters","website":"https://example.com"}})
json.dump({"elements":els}, open(os.path.join(D,"osm.json"),"w"))
feats = []
for i in range(60):
    lat, lng = 1.30 + random.random()*0.1, 103.75 + random.random()*0.2
    name = f"Blk {100+i} Test Market & Food Centre"
    desc = f"<center><table><tr><th>NAME</th><td>{name}</td></tr><tr><th>STATUS</th><td>{'Existing' if i%10 else 'Under Construction'}</td></tr><tr><th>DESCRIPTION</th><td>A neighbourhood hawker centre built in 1980 with 40 stalls.</td></tr></table></center>"
    feats.append({"type":"Feature","geometry":{"type":"Point","coordinates":[lng,lat,0]},"properties":{"Name":f"kml_{i}","Description":desc}})
feats.append({"type":"Feature","geometry":{"type":"Point","coordinates":[103.8326,1.2852,0]},"properties":{"Description":"<table><tr><th>NAME</th><td>Tiong Bahru Market</td></tr><tr><th>STATUS</th><td>Existing</td></tr></table>"}})
json.dump({"type":"FeatureCollection","features":feats}, open(os.path.join(D,"hawkers.json"),"w"))
import datetime as dt
t = dt.date.today()
f = lambda d: d.strftime("%d/%m/%Y")
rows = [{"name":"Tiong Bahru Market","q1_cleaningstartdate":f(t-dt.timedelta(60)),"q1_cleaningenddate":f(t-dt.timedelta(57)),
         "q2_cleaningstartdate":f(t+dt.timedelta(3)),"q2_cleaningenddate":f(t+dt.timedelta(6)),"q3_cleaningstartdate":"TBC","q3_cleaningenddate":"TBC",
         "q4_cleaningstartdate":"","q4_cleaningenddate":"","other_works_startdate":"NA","other_works_enddate":"NA"}]
json.dump(rows, open(os.path.join(D,"closures.json"),"w"))
print("fixtures written")
