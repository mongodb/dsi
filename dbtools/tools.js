// BUILD-5536 Copy baselines
function copy_baselines(tag, from_project, to_project){
    var docs = db.json.find({tag: tag, project_id: from_project});
    print(db.json.count({tag: tag, project_id: to_project}));

    // Remove existing baselines for this tag and project so this script is idempotent.
    db.json.remove({tag: tag, project_id: to_project});

    var count = 0;
    docs.forEach(function(d){
        count++;
        if (count % 100 == 0) {
            print(count);
        }
        delete d._id;
        d.project_id = to_project;
        d.is_patch = true;
        db.json.insert(d);
    });

    print(db.json.count({tag: tag, project_id: to_project}));
}

// SERVER-35071 Create a new variant
function create_new_variant(project, storage_engine, suffix, variant_name_from=null, variant_name_to=null) {
    var docs = db.json.find({project_id: project, task_name: {$regex: suffix}});

    var count = 0;
    docs.forEach(function(d) {
        count++;
        if (count % 100 == 0) {
            print(count);
        }
        delete d._id;
        d.task_name = d.task_name.replace(suffix, "");
        if (variant_name_from) {
            d.variant = d.variant.replace(variant_name_from, variant_name_to);
        };
        d.storage_engine = storage_engine;
        db.json.insert(d)
    })
}
