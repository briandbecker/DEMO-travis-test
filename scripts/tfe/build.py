#!/usr/bin/python3
import os
import time
import requests
import json
import tarfile
import json

TEAM_KEY='Bearer %s' % (os.environ['TFE_TEAM_KEY'])
ORG_NAME=os.environ['TFE_ORG_NAME']
WORKSPACE_NAME=os.environ['TFE_WORKSPACE_NAME']

TFE_SERVER="https://app.terraform.io"
TERRAFORM_FILES="terraform/"

if not os.path.isdir(TERRAFORM_FILES):
    exit(0)

APPLY=False
if os.environ['TRAVIS_PULL_REQUEST'] == "false":
    APPLY=True

def make_tarfile(output_filename, source_dir):
    temp_file=output_filename + "temp"
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir,
            arcname=os.path.basename(source_dir))

def post_to_github_pr(policy_data):
    GITHUB_KEY="token %s" % (os.environ['GITHUB_TOKEN'])

    policy_results = policy_data['data'][0]['attributes']['result']

    github_comment_body = ""
    github_comment_body += "Advisory: %s\n" %(policy_results['advisory-failed'])
    github_comment_body += "Soft Fail: %s\n" %(policy_results['soft-failed'])
    github_comment_body += "Hard Fail: %s\n" %(policy_results['hard-failed'])
    github_comment_body += "Total Fail: %s\n" %(policy_results['total-failed'])
    github_comment_body += "Pass: %s\n" %(policy_results['passed'])
    github_comment_body += "\n\n"
    for p in policy_results['sentinel']['policies']:
        status="Failed"
        if p['result']==True:
            status="Passed"
        github_comment_body += "%s - %s\n" %(p['policy'], status)

    url = "https://api.github.com/repos/%s/issues/%s/comments" % (os.environ['TRAVIS_REPO_SLUG'],os.environ['TRAVIS_PULL_REQUEST'])
    payload = {
                "body": github_comment_body
              }
    headers = {
        'Authorization': GITHUB_KEY,
        "Content-Type": "application/vnd.api+json"
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload))

#-------------------------------------------------------------------------------
# Get workspace id
#-------------------------------------------------------------------------------
print("Get workspace id")
url = TFE_SERVER+"/api/v2/organizations/" + ORG_NAME  + "/workspaces/" + WORKSPACE_NAME
headers = {
    'Authorization': TEAM_KEY,
    "Content-Type": "application/vnd.api+json"
}
r = requests.get(url, headers=headers)
workspace_data = r.json()
print(workspace_data)

#-------------------------------------------------------------------------------
# Create config version
#-------------------------------------------------------------------------------
print("Create Config Version")
url = TFE_SERVER+"/api/v2/workspaces/" + workspace_data['data']['id']  + "/configuration-versions"
payload = {
            "data": {
                "type": "configuration-versions",
                "attributes": {
                    "auto-queue-runs": "false"
                }
            }
        }
headers = {
    'Authorization': TEAM_KEY,
    "Content-Type": "application/vnd.api+json"
}
r = requests.post(url, headers=headers, data=json.dumps(payload))
config_version_data = r.json()
print(r.text)

#-------------------------------------------------------------------------------
# Upload terraform files
#-------------------------------------------------------------------------------
print("Upload terraform files")
make_tarfile("infrastructure.tar.gz",TERRAFORM_FILES)
url = config_version_data['data']['attributes']['upload-url']
files = {'file': open('infrastructure.tar.gz', 'rb')}
headers = {
    'Authorization': TEAM_KEY
}
r = requests.put(url, headers=headers, files=files)
os.remove("infrastructure.tar.gz")

#-------------------------------------------------------------------------------
# Start the build
#-------------------------------------------------------------------------------
print("Start the build")
url = TFE_SERVER+"/api/v2/runs"
payload = {
  "data": {
    "attributes": {
      "is-destroy":False,
      "message": "Pipeline Deploy"
    },
    "type":"runs",
    "relationships": {
      "workspace": {
        "data": {
          "type": "workspaces",
          "id": workspace_data['data']['id']
        }
      }
    }
  }
}

headers = {
    'Authorization': TEAM_KEY,
    "Content-Type": "application/vnd.api+json"
}
r = requests.post(url, headers=headers, data=json.dumps(payload))
run_data = r.json()
print(r.text)

while True:
    print("Sleeping 10 seconds...")
    time.sleep(10)
    print("Checking run status")
    url = TFE_SERVER+"/api/v2/runs/" + run_data['data']['id']
    headers = {
        'Authorization': TEAM_KEY,
        "Content-Type": "application/vnd.api+json"
    }
    r = requests.get(url, headers=headers)
    run_data = r.json()
    run_status=run_data['data']['attributes']['status']
    print("Run Status: %s" %(run_status))

    #---------------------------------------------------------------------------
    # until we have results just keep looping
    #---------------------------------------------------------------------------
    if run_status == "planning" or run_status == "policy_checking":
        continue

    #---------------------------------------------------------------------------
    # ok lets look at the results and put a comment on the PR,
    # but only if we are doing a PR
    #---------------------------------------------------------------------------
    if os.environ['TRAVIS_PULL_REQUEST'] != "false":
        print("Getting policy details")
        url = TFE_SERVER+run_data['data']['relationships']['policy-checks']['links']['related']
        headers = {
            'Authorization': TEAM_KEY,
            "Content-Type": "application/vnd.api+json"
        }
        r = requests.get(url, headers=headers)
        policy_data = r.json()

        if policy_data['data'][0]['attributes']['status'] !='unreachable':
            post_to_github_pr(policy_data)

    #---------------------------------------------------------------------------
    # fail the build
    #---------------------------------------------------------------------------
    if run_status == "errored":
        exit(1)
