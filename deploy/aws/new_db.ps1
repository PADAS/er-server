Param(
  [string]$db_name = $(""),
  [string]$db_host = "at-db.cuts0lhpybwu.us-west-2.rds.amazonaws.com",
  [string]$user = "postgres"
)

if($db_name -like $("")){
      throw "db_name (-db_name) param required."
    }

psql -h $db_host -U $user -v db_name="$db_name" -f .\new_db.sql --set ON_ERROR_STOP=on