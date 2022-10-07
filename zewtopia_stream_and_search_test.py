import redis
from redis.client import Pipeline

#Edit these values to match your Redis Endpoint:
redis_host='192.168.1.20'
redis_port=12000

## This example expects that you have executed the LUA scripts from zew_purchases_stream_event_creator_lua.md
## This example shows a worker in a workergroup processing RedisStream events and turning them into Hashes
## The resulting hashes are then indexed By RediSearch and queried
## run this program by executing:
## python3 zewtopia_stream_and_search_test.py


# Establish the connection to your Redis instance:
myredis = redis.Redis( host=redis_host, port=redis_port, decode_responses=True)

# Establish a Search index (we will query this a bit later)
try:
    myredis.execute_command('FT.DROPINDEX','idx_zew_revenue')
except redis.exceptions.ResponseError as err:
    print(f'FT.DROPINDEX ... {err} continuing on...')
try:
    myredis.execute_command(
    'FT.CREATE','idx_zew_revenue',
    'PREFIX','1','zew:revenue:',
    'SCHEMA','visitor_purchase_item_name','TAG',
    'visitor_purchase_item_cost','NUMERIC','SORTABLE'
    )
except redis.exceptions.ResponseError as err:
    print(f'FT.CREATE ... {err} continuing on...')

# establish python-based stream workergroup:
# this group starts processing at the beginning of the stream:
try:
    #myredis.xgroup_destroy('zew:{batch2}:revenue:stream','group1')
    myredis.xgroup_create('zew:{batch2}:revenue:stream','group1','0-0')
except:
    print('XGROUP_CREATE ... group already exists .. continuing on...')    

# Have a single worker belonging to our group process 10 stream events
# using the > character tells redis to only deliver events unprocessed by this group: 
streamsdict = {'zew:{batch2}:revenue:stream': ">"}
for x in range(10):
    try:
        response = myredis.xreadgroup('group1','processorA',streams=streamsdict,count=1,noack=False)
        eventid = response[0][1][0][0] # the id assigned to the event when it was created
        astring = response[0][1][0][1].get('visitor_purchase') # compound string (attribute of the event)
        itemcost = astring.split(":").pop(0) # by programmer choice the cost and name are stored together
        itemname = astring.split(":").pop(1) # by programmer choice the cost and name are stored together
        # create a Hash record for the processed event:
        myredis.hset('zew:revenue:txid'+eventid,mapping={'visitor_purchase_item_name':itemname,'visitor_purchase_item_cost':itemcost})
        print(myredis.hgetall('zew:revenue:txid'+eventid))
    except:
        print('There are no more items in this stream to be processed by this group')
        length = myredis.execute_command('XLEN',"zew:{batch2}:revenue:stream")
        print(f"There are {length} items in the stream")

# use redis search to query the set of indexed Hashes:
sresult = myredis.execute_command(
'FT.AGGREGATE','idx_zew_revenue',
"@visitor_purchase_item_cost:[1 80]",
"GROUPBY", "1", "@visitor_purchase_item_name", 
"reduce", "SUM", "1", "@visitor_purchase_item_cost", 
"AS", "total_earned", 
"GROUPBY", "2", "@visitor_purchase_item_name", "@total_earned",
"SORTBY","2","@total_earned","DESC",
"LIMIT", "0", "100"
)

for c in range(len(sresult)):
    print(sresult[c])

qstring = ''' "FT.AGGREGATE" "idx_zew_revenue"
          "@visitor_purchase_item_cost:[1 80]"
          "GROUPBY" "1" "@visitor_purchase_item_name"
          "reduce" "SUM" "1" "@visitor_purchase_item_cost"
          "AS" "total_earned"
          "GROUPBY" "2" "@visitor_purchase_item_name" "@total_earned"
          "SORTBY" "2" "@total_earned" "DESC"
          "LIMIT" "0" "20" '''

print(f"Above results came from this query: {qstring}")
print("\n Why not use Redis-cli or RedisInsight to test out some other queries?")