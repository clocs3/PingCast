def IMAGE_DEFS = [
  [id: 'nginx-rtmp-aws',    dir: 'media/aws-burst/nginx-rtmp'],
  [id: 'stream-controller-aws', dir: 'media/aws-burst/stream-controller'],
  [id: 'ffmpeg-hls-aws',    dir: 'media/aws-burst/ffmpeg'],
  [id: 's3-uploader',       dir: 'media/aws-burst/s3-uploader'],
]

pipeline {
  agent any
  options { timestamps() }

  environment {
    REGISTRY = "registry.example.com"
    PROJECT  = "pingcast"

    DEPLOY_REPO_URL = "ssh://git@gitlab.example.com:2222/pingcast/deploy-vpc1.git"
    DEPLOY_BRANCH   = "main"
    SHARED_DEPLOY_REPO_URL = "ssh://git@gitlab.example.com:2222/pingcast/deploy-vpc2.git"
    SHARED_DEPLOY_BRANCH   = "main"

    KUSTOM_FILE       = "apps/pingcast/media/overlays/kustomization.yaml"
    BASE_WORKLOAD_FILE = "apps/pingcast/media/base/workloads.yaml"
  }

  stages {
    stage("Init (Compute GIT_SHA)") {
      steps {
        script {
          def sha = (env.GIT_COMMIT ?: "").trim()
          if (sha) {
            env.GIT_SHA = sha.take(12)
          } else {
            env.GIT_SHA = sh(script: "git rev-parse --short=12 HEAD", returnStdout: true).trim()
          }
          if (!env.GIT_SHA) {
            error("Cannot compute GIT_SHA")
          }

          def knownDirs = IMAGE_DEFS.collect { it.dir }
          def baseCommit = (env.GIT_PREVIOUS_SUCCESSFUL_COMMIT ?: env.GIT_PREVIOUS_COMMIT ?: "").trim()
          if (!baseCommit) {
            try {
              baseCommit = sh(script: "git rev-parse --verify HEAD~1", returnStdout: true).trim()
            } catch (ignored) {
              baseCommit = ""
            }
          }

          def changedFiles = []
          if (baseCommit) {
            def raw = sh(script: "git diff --name-only ${baseCommit}..HEAD", returnStdout: true).trim()
            if (raw) {
              changedFiles = raw.split("\\n") as List
            }
          }

          def selected = [] as Set
          boolean forceAll = !baseCommit

          if (!forceAll) {
            IMAGE_DEFS.each { image ->
              if (changedFiles.any { it == image.dir || it.startsWith("${image.dir}/") }) {
                selected << image.id
              }
            }

            boolean unknownImpactChange = changedFiles.any { f ->
              !knownDirs.any { d -> f == d || f.startsWith("${d}/") }
            }
            if (unknownImpactChange) {
              forceAll = true
            }
          }

          if (forceAll) {
            selected = IMAGE_DEFS.collect { it.id } as Set
          }

          def orderedSelected = IMAGE_DEFS.collect { it.id }.findAll { selected.contains(it) }
          env.BUILD_IMAGE_NAMES = orderedSelected.join(",")
          env.BUILD_IMAGE_COUNT = orderedSelected.size().toString()

          echo "GIT_SHA=${env.GIT_SHA}"
          echo "IMAGE_TAG=${env.GIT_SHA}"
          echo "BASE_COMMIT=${baseCommit ?: 'N/A'}"
          echo "CHANGED_FILES=${changedFiles ? changedFiles.join(', ') : 'N/A (first build or no diff)'}"
          echo "BUILD_IMAGE_NAMES=${env.BUILD_IMAGE_NAMES ?: 'none'}"
        }
      }
    }

    stage("Script Lint (sh -n)") {
      steps {
        sh '''
          set -eux
          find . -type f -name "*.sh" -print0 | xargs -0 -r -n 1 sh -n
        '''
      }
    }

    stage("Build Images") {
      when {
        expression { env.BUILD_IMAGE_COUNT != "0" }
      }
      steps {
        script {
          def targets = (env.BUILD_IMAGE_NAMES ?: "").tokenize(",")
          for (def imageId : targets) {
            def meta = IMAGE_DEFS.find { it.id == imageId }
            sh """
              set -eux
              docker build --pull -t "${env.REGISTRY}/${env.PROJECT}/${meta.id}:${env.GIT_SHA}" "./${meta.dir}"
            """
          }
        }
      }
    }

    stage("Trivy Scan (HIGH/CRITICAL fail)") {
      when {
        expression { env.BUILD_IMAGE_COUNT != "0" }
      }
      steps {
        script {
          def targets = (env.BUILD_IMAGE_NAMES ?: "").tokenize(",")
          for (def imageId : targets) {
            sh """
              set -eux
              trivy image --severity HIGH,CRITICAL --exit-code 1 --ignore-unfixed --timeout 10m "${env.REGISTRY}/${env.PROJECT}/${imageId}:${env.GIT_SHA}"
            """
          }
        }
      }
    }

    stage("Harbor Login & Push") {
      when {
        expression { env.BUILD_IMAGE_COUNT != "0" }
      }
      environment {
        HARBOR_CREDS = credentials('HARBOR_CICD_RW')
      }
      steps {
        sh '''
          set -eux
          echo "$HARBOR_CREDS_PSW" | docker login "$REGISTRY" -u "$HARBOR_CREDS_USR" --password-stdin
        '''
        script {
          def targets = (env.BUILD_IMAGE_NAMES ?: "").tokenize(",")
          for (def imageId : targets) {
            sh """
              set -eux
              docker push "${env.REGISTRY}/${env.PROJECT}/${imageId}:${env.GIT_SHA}"
            """
          }
        }
      }
    }

    stage("Update Deploy Repo (GitOps)") {
      when {
        expression { env.BUILD_IMAGE_COUNT != "0" }
      }
      steps {
        withCredentials([
          sshUserPrivateKey(credentialsId: 'deploy', keyFileVariable: 'DEPLOY_KEYFILE'),
          file(credentialsId: 'GITLAB_KNOWN_HOSTS', variable: 'GITLAB_KNOWN_HOSTS')
        ]) {
          sh '''
            set -eux

            install -m 700 -d /var/jenkins_home/.ssh
            install -m 600 "$GITLAB_KNOWN_HOSTS" /var/jenkins_home/.ssh/known_hosts

            export GIT_SSH_COMMAND="ssh -i $DEPLOY_KEYFILE -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -p 2222"

            update_image_tag() {
              file="$1"
              image="$2"
              tag="$3"
              awk -v image="$image" -v tag="$tag" '
                BEGIN { in_block=0; updated=0 }
                {
                  if ($0 ~ /^[[:space:]]*-[[:space:]]*name:[[:space:]]*/) {
                    name_line=$0
                    sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/, "", name_line)
                    gsub(/[[:space:]]+$/, "", name_line)
                    in_block=(name_line==image)
                  } else if ($0 ~ /^[[:space:]]*name:[[:space:]]*/) {
                    name_line=$0
                    sub(/^[[:space:]]*name:[[:space:]]*/, "", name_line)
                    gsub(/[[:space:]]+$/, "", name_line)
                    in_block=(name_line==image)
                  }

                  if (in_block && $0 ~ /^[[:space:]]*newTag:[[:space:]]*/) {
                    sub(/newTag:[[:space:]]*.*/, "newTag: " tag)
                    in_block=0
                    updated=1
                  }
                  print
                }
                END {
                  if (!updated) exit 42
                }
              ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
            }

            update_env_image() {
              file="$1"
              env_name="$2"
              image="$3"
              awk -v env_name="$env_name" -v image="$image" '
                BEGIN { in_env=0; updated=0 }
                {
                  if ($0 ~ /^[[:space:]]*-[[:space:]]*name:[[:space:]]*/) {
                    name_line=$0
                    sub(/^[[:space:]]*-[[:space:]]*name:[[:space:]]*/, "", name_line)
                    gsub(/[[:space:]]+$/, "", name_line)
                    in_env=(name_line==env_name)
                    print
                    next
                  }

                  if (in_env && $0 ~ /^[[:space:]]*value:[[:space:]]*/) {
                    indent=""
                    if (match($0, /^[[:space:]]*/)) {
                      indent=substr($0, RSTART, RLENGTH)
                    }
                    print indent "value: " image
                    in_env=0
                    updated=1
                    next
                  }

                  print
                }
                END {
                  if (!updated) exit 42
                }
              ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
            }

            sync_deploy_repo() {
              repo_url="$1"
              branch="$2"
              repo_dir="$3"
              image_names="$4"

              rm -rf "$repo_dir"
              git clone "$repo_url" "$repo_dir"
              cd "$repo_dir"
              git checkout "$branch"

              test -f "$KUSTOM_FILE"
              test -f "$BASE_WORKLOAD_FILE"

              OLD_IFS="$IFS"
              IFS=','
              for image_id in $image_names; do
                [ -n "$image_id" ] || continue
                full_image="$REGISTRY/$PROJECT/$image_id"
                tag_updated=0

                if update_image_tag "$KUSTOM_FILE" "$full_image" "$GIT_SHA"; then
                  echo "Updated tag: $full_image -> $GIT_SHA"
                  tag_updated=1
                elif update_image_tag "$KUSTOM_FILE" "$image_id" "$GIT_SHA"; then
                  echo "Updated tag: $image_id -> $GIT_SHA"
                  tag_updated=1
                fi

                case "$image_id" in
                  ffmpeg-hls-aws)
                    update_env_image "$BASE_WORKLOAD_FILE" "FFMPEG_IMAGE" "$full_image:$GIT_SHA"
                    echo "Updated env: FFMPEG_IMAGE -> $full_image:$GIT_SHA"
                    ;;
                  s3-uploader)
                    update_env_image "$BASE_WORKLOAD_FILE" "FFMPEG_SIDECAR_IMAGE" "$full_image:$GIT_SHA"
                    echo "Updated env: FFMPEG_SIDECAR_IMAGE -> $full_image:$GIT_SHA"
                    ;;
                esac

                if [ "$tag_updated" -ne 1 ] && [ "$image_id" != "s3-uploader" ]; then
                  echo "ERROR: image entry not found in $KUSTOM_FILE for '$full_image' or '$image_id'"
                  exit 1
                fi
              done
              IFS="$OLD_IFS"

              git diff -- "$KUSTOM_FILE" "$BASE_WORKLOAD_FILE" || true

              if git diff --quiet; then
                echo "No changes in $repo_url"
                cd ..
                rm -rf "$repo_dir"
                return 0
              fi

              git config user.email "jenkins@pingcast.local"
              git config user.name  "jenkins"

              git add "$KUSTOM_FILE" "$BASE_WORKLOAD_FILE"
              git commit -m "deploy: set media image tags to ${GIT_SHA} (${image_names})"

              for i in 1 2 3; do
                if git push origin "$branch"; then
                  cd ..
                  rm -rf "$repo_dir"
                  return 0
                fi
                echo "Push failed, retry with rebase... ($i/3)"
                git pull --rebase origin "$branch"
              done

              echo "ERROR: git push failed after retries"
              exit 1
            }

            sync_deploy_repo "$DEPLOY_REPO_URL" "$DEPLOY_BRANCH" "deploy-repo-vpc1" "$BUILD_IMAGE_NAMES"

            shared_images=""
            OLD_IFS="$IFS"
            IFS=','
            for image_id in $BUILD_IMAGE_NAMES; do
              if [ "$image_id" = "s3-uploader" ]; then
                shared_images="${shared_images:+$shared_images,}$image_id"
              fi
            done
            IFS="$OLD_IFS"

            if [ -n "$shared_images" ]; then
              sync_deploy_repo "$SHARED_DEPLOY_REPO_URL" "$SHARED_DEPLOY_BRANCH" "deploy-repo-vpc2" "$shared_images"
            fi
          '''
        }
      }
    }

    stage("Info (What to check right now)") {
      steps {
        script {
          def targets = (env.BUILD_IMAGE_NAMES ?: "").tokenize(",")
          if (targets.isEmpty()) {
            echo "No image build required for this commit."
          } else {
            echo "Built/Pushed tags:"
            targets.each { imageId ->
              echo "  ${env.REGISTRY}/${env.PROJECT}/${imageId}:${env.GIT_SHA}"
            }
            echo "Deploy repo file updated: ${env.KUSTOM_FILE}"
          }
        }
      }
    }
  }

  post {
    always {
      sh '''
        set +e
        docker logout "$REGISTRY" || true
      '''
      script {
        def targets = (env.BUILD_IMAGE_NAMES ?: "").tokenize(",")
        for (def imageId : targets) {
          sh """
            set +e
            docker rmi "${env.REGISTRY}/${env.PROJECT}/${imageId}:${env.GIT_SHA}" || true
          """
        }
      }
      sh '''
        set +e
        docker builder prune -af || true
      '''
    }
  }
}
