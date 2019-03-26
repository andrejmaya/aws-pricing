import json, boto3, time, requests, decimal, cStringIO, csv, logging, os
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
  
  if event['offerCode'] == 'AmazonEC2':
    prices = []
    for region in ['eu-central-1']:
      offer = download_offer(region)
      prices += extract_prices(offer)

    upload_prices(prices)
    

def download_offer(region):
  #with open('prices.json') as f:
  #  response = json.load(f)
  #return response
  
  response = requests.get("https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/"+ region +"/index.json")
  return json.loads(response.text)

def filter_products(products):
  filtered = []

  # Only interested in shared tenancy, linux instances
  for sku, product in products:
    a = product['attributes']
    if not ('instanceType' in a and
            'location' in a and
            'operatingSystem' in a and
            'tenancy' in a and
            'preInstalledSw' in a and
            'capacitystatus' in a and
            a['tenancy'] == 'Shared' and
            a['capacitystatus'] == 'Used' and
            a['preInstalledSw'] == 'NA' and
            a['operatingSystem'] == 'Linux' and
            a['location'] in ['EU (Frankfurt)','EU (Ireland)'] and
            a['instanceType'] in ['m4.xlarge','r4.4xlarge','t2.micro','t2.small']):
      continue

    a['sku'] = sku
    filtered.append(a)

  return filtered

def extract_prices(offer):
  terms = offer['terms']
  products = offer['products'].items()

  instances = []
  instancesTmp = {}
  for a in filter_products(products):
    cost_OnDemand = 0.0
    cost_1y_no_up = 0.0
    cost_3y_no_up = 0.0
    cost_1y_all_up = 0.0
    cost_3y_all_up = 0.0
    #logger.info("location: {}".format(a['location'])) 

    term_OnDemand = terms['OnDemand'][a['sku']].items()[0][1]
    cost_OnDemand = float(term_OnDemand['priceDimensions'].items()[0][1]['pricePerUnit']['USD'])
    
    if a['sku'] in terms['Reserved']:
      for reservedItem in terms['Reserved'][a['sku']].items():
        reserved = reservedItem[1]
        if reserved['termAttributes']['LeaseContractLength'] == '1yr' and reserved['termAttributes']['OfferingClass'] == 'standard' and reserved['termAttributes']['PurchaseOption'] == 'No Upfront':
          cost_1y_no_up = float(reserved['priceDimensions'].items()[0][1]['pricePerUnit']['USD'])
        elif reserved['termAttributes']['LeaseContractLength'] == '3yr' and reserved['termAttributes']['OfferingClass'] == 'standard' and reserved['termAttributes']['PurchaseOption'] == 'No Upfront':
          cost_3y_no_up = float(reserved['priceDimensions'].items()[0][1]['pricePerUnit']['USD'])
        elif reserved['termAttributes']['LeaseContractLength'] == '1yr' and reserved['termAttributes']['OfferingClass'] == 'standard' and reserved['termAttributes']['PurchaseOption'] == 'All Upfront':
          cost_1y_all_up = float(reserved['priceDimensions'].items()[0][1]['pricePerUnit']['USD'])
        elif reserved['termAttributes']['LeaseContractLength'] == '3yr' and reserved['termAttributes']['OfferingClass'] == 'standard' and reserved['termAttributes']['PurchaseOption'] == 'All Upfront':
          cost_3y_all_up = float(reserved['priceDimensions'].items()[0][1]['pricePerUnit']['USD'])        

    if cost_OnDemand != 0.0:
      info = {"type" : a['instanceType'], 
              "cost_OnDemand" : cost_OnDemand,
              "cost_1y_no_up" : str(cost_1y_no_up*730).replace(".",","),
              "cost_3y_no_up" : str(cost_3y_no_up*730).replace(".",","),
              "cost_1y_all_up" : str(cost_1y_all_up/12).replace(".",","),
              "cost_3y_all_up" : str(cost_3y_all_up/36).replace(".",","),
              "sku" : a['sku'],
              "location" : a['location']}
      ident = a['location']+"-"+info['type']  
      if not ident in instancesTmp:
        instances.append(info) 
        instancesTmp[a['location']+"-"+info['type']] = {}
      
  
  return instances

def upload_prices(prices):
  
  logger.info("{}".format(prices)) 
  
  with open("/tmp/data.csv", "w") as file:
      csv_file = csv.writer(file, delimiter=";")
      csv_file.writerow(['sku','location', 'type', 'cost_OnDemand', 'cost_1y_no_up', 'cost_3y_no_up', 'cost_1y_all_up', 'cost_3y_all_up'])
      for item in prices:
        csv_file.writerow([item['sku'],item['location'],item['type'],item['cost_OnDemand'],item['cost_1y_no_up'],item['cost_3y_no_up'],item['cost_1y_all_up'],item['cost_3y_all_up']])
  
  csv_binary = open('/tmp/data.csv', 'rb').read()
    
  s3 = boto3.client('s3')
  s3.put_object(ACL='public-read', Body=csv_binary, ContentType='text/csv', 
                Bucket=os.environ['BUCKET_NAME'], Key='prices.csv')                
                
